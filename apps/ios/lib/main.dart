import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';

const appOrigin = 'https://agroamigo-demo-9a04.azurewebsites.net';
const brandGreen = Color(0xff22643f);
const paper = Color(0xfff2f4ef);

bool isAppUrl(Uri url) =>
    url.scheme == 'https' &&
    url.host == Uri.parse(appOrigin).host &&
    url.port == 443 &&
    url.userInfo.isEmpty;

void main() => runApp(const AgroAmigoApp());

class AgroAmigoApp extends StatelessWidget {
  const AgroAmigoApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'AgroAmigo',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: brandGreen),
      scaffoldBackgroundColor: paper,
    ),
    home: const FarmBrowser(),
  );
}

class FarmBrowser extends StatefulWidget {
  const FarmBrowser({super.key});

  @override
  State<FarmBrowser> createState() => FarmBrowserState();
}

class FarmBrowserState extends State<FarmBrowser> with WidgetsBindingObserver {
  late final WebViewController controller;
  bool loading = true;
  bool failed = false;
  bool canGoBack = false;
  bool sharing = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(paper)
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: _navigate,
          onPageStarted: (_) {
            if (mounted) {
              setState(() {
                loading = true;
                failed = false;
              });
            }
          },
          onPageFinished: (_) async {
            await _syncSafeArea();
            await _updateBack();
            if (mounted) setState(() => loading = false);
          },
          onUrlChange: (_) => unawaited(_updateBack()),
          onWebResourceError: (error) {
            // WKWebView reports cancellation when we hand a download/export
            // to the native share sheet or replace an in-flight navigation.
            if (error.errorCode == -999 || error.errorCode == 102) {
              if (mounted && error.isForMainFrame == true) {
                setState(() => loading = false);
              }
              return;
            }
            if (error.isForMainFrame == true && mounted) {
              setState(() {
                failed = true;
                loading = false;
              });
            }
          },
        ),
      );
    final platform = controller.platform;
    if (kDebugMode) {
      unawaited(
        controller.setOnConsoleMessage((message) {
          debugPrint('AgroAmigo web: ${message.message}');
        }),
      );
    }
    if (platform is WebKitWebViewController) {
      unawaited(platform.setAllowsBackForwardNavigationGestures(true));
    }
    unawaited(_start());
  }

  // Flutter's embedded WKWebView can report CSS env(safe-area-inset-bottom)
  // as zero. Pass only the native layout measurement to our trusted page.
  Future<void> _syncSafeArea() async {
    if (!mounted) return;
    final view = View.of(context);
    final bottom = view.viewPadding.bottom / view.devicePixelRatio;
    final current = Uri.tryParse(await controller.currentUrl() ?? '');
    if (current == null || !isAppUrl(current)) return;
    try {
      await controller.runJavaScript(
        "document.documentElement.style.setProperty('--agro-safe-bottom', '${bottom}px')",
      );
    } catch (_) {
      // The next finished navigation reapplies the value if the document changed.
    }
  }

  @override
  void didChangeMetrics() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_syncSafeArea());
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _start() async {
    final agent = await controller.getUserAgent();
    await controller.setUserAgent('${agent ?? ''} AgroAmigoIOS/1.0');
    await controller.loadRequest(Uri.parse(appOrigin));
  }

  Future<void> _updateBack() async {
    final back = await controller.canGoBack();
    if (mounted) setState(() => canGoBack = back);
  }

  Future<NavigationDecision> _navigate(NavigationRequest request) async {
    final url = Uri.tryParse(request.url);
    if (url == null) return NavigationDecision.prevent;
    if (url.scheme == 'agroamigo-export') {
      final current = Uri.tryParse(await controller.currentUrl() ?? '');
      if (request.isMainFrame && current != null && isAppUrl(current)) {
        unawaited(_exportScenario(url));
      }
      return NavigationDecision.prevent;
    }
    if (isAppUrl(url)) {
      // Only top-level document links invoke the native share sheet. The PDF
      // viewer's fetch requests continue directly to the same Azure origin.
      if (request.isMainFrame &&
          RegExp(r'^/api/evidence/[^/]+/content$').hasMatch(url.path)) {
        unawaited(_downloadDocument(url));
        return NavigationDecision.prevent;
      }
      return NavigationDecision.navigate;
    }
    if (url.scheme == 'https' && request.isMainFrame) {
      unawaited(_openExternal(url));
    }
    return NavigationDecision.prevent;
  }

  Future<void> _openExternal(Uri url) async {
    try {
      if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
        _message('No se pudo abrir la fuente. Intenta de nuevo.');
      }
    } catch (_) {
      _message('No se pudo abrir la fuente. Intenta de nuevo.');
    }
  }

  void _message(String message) {
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _share(Uint8List bytes, String filename, String mime) async {
    if (!mounted) return;
    final box = context.findRenderObject() as RenderBox;
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile.fromData(bytes, mimeType: mime)],
        fileNameOverrides: [filename],
        title: 'Guardar o compartir',
        sharePositionOrigin: box.localToGlobal(Offset.zero) & box.size,
      ),
    );
  }

  Future<void> _exportScenario(Uri url) async {
    if (sharing) return;
    sharing = true;
    try {
      if (url.host != 'scenario') throw const FormatException();
      final raw = url.queryParameters['data'] ?? '';
      final bytes = Uint8List.fromList(utf8.encode(raw));
      if (bytes.isEmpty || bytes.length > 250000 || jsonDecode(raw) is! Map) {
        throw const FormatException();
      }
      await _share(bytes, 'escenario-agroamigo.json', 'application/json');
    } catch (_) {
      _message('No se pudo guardar el escenario. Intenta de nuevo.');
    } finally {
      sharing = false;
    }
  }

  Future<void> _downloadDocument(Uri url) async {
    if (sharing) return;
    sharing = true;
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 20);
    try {
      _message('Preparando documento…');
      final request = await client.getUrl(url);
      request.followRedirects = false;
      final response = await request.close().timeout(
        const Duration(seconds: 30),
      );
      if (response.statusCode != 200) throw const HttpException('Unavailable');
      final mime = response.headers.contentType?.mimeType ?? '';
      const extensions = {
        'application/pdf': 'pdf',
        'application/json': 'json',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            'xlsx',
        'text/plain': 'txt',
      };
      final ext = extensions[mime];
      if (ext == null) throw const FormatException('Unsupported document');
      final bytes = BytesBuilder(copy: false);
      await for (final chunk in response.timeout(const Duration(seconds: 30))) {
        bytes.add(chunk);
        if (bytes.length > 50 * 1024 * 1024) {
          throw const FormatException('Document exceeds 50 MB');
        }
      }
      await _share(bytes.takeBytes(), 'fuente-agroamigo.$ext', mime);
    } catch (_) {
      _message('No se pudo descargar el documento. Revisa tu conexión.');
    } finally {
      client.close(force: true);
      sharing = false;
    }
  }

  @override
  Widget build(BuildContext context) => AnnotatedRegion<SystemUiOverlayStyle>(
    value: SystemUiOverlayStyle.dark,
    child: Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        // WKWebView and the web tab bar extend behind the home indicator.
        // The native inset is passed to CSS to clear the home indicator.
        bottom: false,
        child: Stack(
          fit: StackFit.expand,
          children: [
            WebViewWidget(controller: controller),
            if (loading)
              const Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: LinearProgressIndicator(color: brandGreen, minHeight: 2),
              ),
            if (failed)
              ColoredBox(
                color: paper,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.cloud_off_outlined,
                          size: 48,
                          color: brandGreen,
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Revisa tu conexión',
                          style: TextStyle(fontSize: 24),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Necesitas internet para consultar precios y fuentes. Tus datos guardados siguen en este dispositivo.',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),
                        FilledButton(
                          onPressed: () {
                            setState(() {
                              failed = false;
                              loading = true;
                            });
                            controller.loadRequest(Uri.parse(appOrigin));
                          },
                          child: const Text('Intentar de nuevo'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}
