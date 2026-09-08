import 'dart:convert';
import 'package:flutter/foundation.dart';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:webview_flutter/webview_flutter.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;

  testWidgets('iPhone layout, Azure data, persistence, back and archived PDF', (
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
    final view = tester.view;
    final screenHeight = view.physicalSize.height / view.devicePixelRatio;
    final topInset = view.padding.top / view.devicePixelRatio;
    final webRect = tester.getRect(find.byType(WebViewWidget));
    expect(webRect.top, closeTo(topInset, 1));
    expect(
      webRect.bottom,
      closeTo(screenHeight, 1),
      reason: 'Web content must extend to the bottom edge of the iPhone',
    );
    Future<void> checkTabs() async {
      await until('document.querySelector(".mobile-nav") !== null');
      await until(
        'getComputedStyle(document.querySelector(".mobile-nav")).position === "fixed"',
      );
      await until(
        'parseFloat(getComputedStyle(document.querySelector(".mobile-nav")).paddingBottom) >= ${view.padding.bottom / view.devicePixelRatio - 1}',
      );
      final metrics = await web.runJavaScriptReturningResult('''JSON.stringify({
        viewport: [innerWidth, innerHeight],
        nav: document.querySelector('.mobile-nav').getBoundingClientRect().toJSON(),
        padding: getComputedStyle(document.querySelector('.mobile-nav')).paddingBottom,
        tabs: [...document.querySelectorAll('.mobile-nav a')].map(a => a.getBoundingClientRect().width),
        scrollWidth: document.documentElement.scrollWidth,
        viewportMeta: document.querySelector('meta[name=viewport]').content
      })''');
      debugPrint(
        'Phone tab metrics: $metrics; native bottom: ${view.padding.bottom / view.devicePixelRatio}',
      );
      await binding.takeScreenshot('ios-layout-metrics');
      expect(
        await web.runJavaScriptReturningResult('''(() => {
        const nav = document.querySelector('.mobile-nav');
        const box = nav.getBoundingClientRect();
        const tabs = [...nav.querySelectorAll('a')].map(a => a.getBoundingClientRect());
        const bottom = parseFloat(getComputedStyle(nav).paddingBottom);
        return Math.abs(box.bottom - innerHeight) < 2 &&
          Math.abs(box.width - innerWidth) < 2 &&
          tabs.every(t => Math.abs(t.width - tabs[0].width) < 1) &&
          bottom >= ${view.padding.bottom / view.devicePixelRatio - 1} &&
          document.documentElement.scrollWidth <= innerWidth;
      })()'''),
        true,
        reason: 'Tabs must fill the screen and clear the home indicator',
      );
    }

    await checkTabs();
    await binding.takeScreenshot('ios-layout-home');
    await web.runJavaScript(
      'document.querySelector(".mobile-nav a[href=\\"/markets\\"]").click()',
    );
    await until(
      'location.pathname === "/markets" && document.querySelector(".mobile-nav a[href=\\"/markets\\"]").hasAttribute("aria-current")',
    );
    await checkTabs();
    expect(
      tester.getRect(find.byType(WebViewWidget)),
      webRect,
      reason:
          'Following a link must not shrink the web view for a second back bar',
    );
    await binding.takeScreenshot('ios-layout-markets');
    await web.runJavaScript(
      r'document.querySelector("a[href=\"/products\"]").click()',
    );
    await until(
      'location.pathname === "/products" && document.body.innerText.includes("Café")',
    );
    expect(await web.currentUrl(), contains('/products'));
    await checkTabs();
    await binding.takeScreenshot('ios-layout-products');

    // This suite runs only on an explicitly created disposable test simulator.
    await web.runJavaScript(
      'localStorage.setItem("agroamigo-location-v1", JSON.stringify({point:{latitude:1.9,longitude:-76.1},municipalityId:"41551",name:"Pin de prueba"}))',
    );
    await web.loadRequest(Uri.parse('${app.appOrigin}/farm'));
    await until(
      'document.querySelector(".zone-map")?.dataset.ready === "true"',
    );
    await until(
      'Number(document.querySelector(".zone-map")?.dataset.tiles) > 0',
    );
    await until(
      'document.querySelector(".zone-reading")?.textContent.includes("Lluvia habitual")',
    );
    final profile = await web.runJavaScriptReturningResult(
      'localStorage.getItem("agroamigo-location-v1") || ""',
    );
    await web.reload();
    await until(
      'document.querySelector(".zone-map")?.dataset.pinLat === "1.9"',
    );
    expect(
      await web.runJavaScriptReturningResult(
        'localStorage.getItem("agroamigo-location-v1") || ""',
      ),
      profile,
    );
    await checkTabs();
    await web.runJavaScript(
      'document.querySelector(".zone-map").scrollIntoView()',
    );
    await binding.takeScreenshot('ios-location-map');
    await web.runJavaScript('document.getElementById("clean-tab").click()');
    await until('document.querySelector(".clean-sheet") !== null');
    await until(
      'Array.from(document.querySelectorAll("a.evidence-link")).some(a => a.textContent.includes("Ver costo publicado"))',
    );
    await web.runJavaScript(
      'Array.from(document.querySelectorAll("a.evidence-link")).find(a => a.textContent.includes("Ver costo publicado")).click()',
    );
    await until('document.querySelector("dialog[open]") !== null');
    await until(
      r'document.querySelector("canvas[data-rendered=true][aria-label=\"Página 6 del PDF\"]") !== null && document.querySelector(".pdf-text")?.textContent.includes("1,550,805")',
    );
    await web.runJavaScript(
      'document.querySelector(".pdf-viewer").scrollIntoView()',
    );
    await tester.pump(const Duration(seconds: 1));
    await binding.takeScreenshot('ios-evidence');
    expect(state.canGoBack, isTrue);
    await web.goBack();
    await until('document.querySelector("dialog[open]") === null');
    await until('document.querySelector(".clean-sheet") !== null');

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
