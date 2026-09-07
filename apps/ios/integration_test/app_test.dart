import 'dart:convert';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;

  testWidgets('Azure app, local persistence, native back and archived PDF', (
    tester,
  ) async {
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final state = tester.state<app.FarmBrowserState>(
      find.byType(app.FarmBrowser),
    );
    final web = state.controller;
    Future<void> until(String expression) async {
      final deadline = DateTime.now().add(const Duration(seconds: 90));
      while (DateTime.now().isBefore(deadline)) {
        final result = await web
            .runJavaScriptReturningResult('Boolean($expression)')
            .timeout(const Duration(seconds: 10));
        if (result == true || result == 'true') return;
        await tester.pump(const Duration(milliseconds: 300));
      }
      final body = await web.runJavaScriptReturningResult(
        'document.body.innerText',
      );
      fail('Timed out waiting for $expression; page: $body');
    }

    await until(
      r'document.body.innerText.includes("AgroAmigo") && document.querySelectorAll("a[href=\"/products\"]").length > 0',
    );
    await web.runJavaScript(
      r'document.querySelector("a[href=\"/products\"]").click()',
    );
    await until(
      'location.pathname === "/products" && document.body.innerText.includes("Café")',
    );
    expect(await web.currentUrl(), contains('/products'));

    await web.runJavaScript('localStorage.removeItem("agroamigo-farm-v1")');
    await web.loadRequest(Uri.parse('${app.appOrigin}/farm'));
    await until(
      'Array.from(document.querySelectorAll("button")).some(b => b.innerText.includes("Pitalito") && !b.disabled)',
    );
    await web.runJavaScript(
      'Array.from(document.querySelectorAll("button")).find(b => b.innerText.includes("Pitalito")).click()',
    );
    await until('document.body.innerText.includes("Tu plan para esta semana")');
    final profile = await web.runJavaScriptReturningResult(
      'localStorage.getItem("agroamigo-farm-v1") || ""',
    );
    expect(profile.toString().length, greaterThan(20));
    await web.reload();
    await until('document.body.innerText.includes("Pitalito")');
    expect(
      await web.runJavaScriptReturningResult(
        'localStorage.getItem("agroamigo-farm-v1") || ""',
      ),
      profile,
    );

    await web.loadRequest(
      Uri.parse('${app.appOrigin}/evidence/coffee-cost-benchmark?page=6'),
    );
    await until('document.body.innerText.includes("Comprueba el dato")');
    await until(
      r'document.querySelector("canvas[data-rendered=true][aria-label=\"Página 6 del PDF\"]") !== null && document.querySelector(".pdf-text")?.textContent.includes("1,550,805")',
    );
    final headings = await web.runJavaScriptReturningResult(
      'JSON.stringify(Array.from(document.querySelectorAll("h2")).map(e=>e.innerText))',
    );
    expect(headings.toString(), contains('FEPCaf'));
    await web.runJavaScript(
      'document.querySelector(".pdf-viewer").scrollIntoView()',
    );
    await tester.pump(const Duration(seconds: 1));
    await binding.takeScreenshot('ios-evidence');
    expect(find.text('Volver'), findsOneWidget);
    await tester.tap(find.text('Volver'));
    await until(
      'location.pathname === "/farm" && document.body.innerText.includes("Tu plan para esta semana")',
    );

    // Inspect all exported data through the same native navigation path used by
    // the budget UI. The share sheet is left open for simulator visual QA.
    const payload = {
      'crop': 'Café',
      'totalCost': 600000,
      'sourceDocuments': ['coffee-cost-benchmark'],
    };
    final uri = Uri(
      scheme: 'agroamigo-export',
      host: 'scenario',
      queryParameters: {'data': jsonEncode(payload)},
    );
    await web.runJavaScript(
      'window.location.href = ${jsonEncode(uri.toString())}',
    );
    await tester.pump(const Duration(seconds: 2));
    expect(await web.currentUrl(), startsWith(app.appOrigin));
    expect(
      state.failed,
      isFalse,
      reason: 'Export cancellation must not show a connection error',
    );
    expect(
      state.loading,
      isFalse,
      reason: 'Export must not leave the loading bar running',
    );
    await binding.takeScreenshot('ios-export');
  });
}
