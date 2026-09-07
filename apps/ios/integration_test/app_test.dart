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
      'document.querySelector(".mobile-nav a[href=\\"/saved\\"]").click()',
    );
    await until(
      'location.pathname === "/saved" && document.querySelector(".mobile-nav a[href=\\"/saved\\"]").hasAttribute("aria-current")',
    );
    await checkTabs();
    expect(
      tester.getRect(find.byType(WebViewWidget)),
      webRect,
      reason:
          'Following a link must not shrink the web view for a second back bar',
    );
    await binding.takeScreenshot('ios-layout-saved');
    await web.runJavaScript(
      r'document.querySelector("a[href=\"/products\"]").click()',
    );
    await until(
      'location.pathname === "/products" && document.body.innerText.includes("Café")',
    );
    expect(await web.currentUrl(), contains('/products'));
    await checkTabs();
    await binding.takeScreenshot('ios-layout-products');

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
    await web.runJavaScript('window.scrollTo(0, 0)');
    await binding.takeScreenshot('ios-layout-farm');

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
    expect(state.canGoBack, isTrue);
    await web.runJavaScript('document.querySelector(".back-button").click()');
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
