import 'dart:convert';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  binding.shouldPropagateDevicePointerEvents = true;
  testWidgets('Physical map drag leaves filtered map open', (tester) async {
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final web = tester.state<app.FarmBrowserState>(find.byType(app.FarmBrowser)).controller;
    Future<bool> ready(String expression) async =>
        await web.runJavaScriptReturningResult('Boolean($expression)') == true;
    Future<void> until(String expression) async {
      final end = DateTime.now().add(const Duration(seconds: 90));
      while (DateTime.now().isBefore(end)) {
        if (await ready(expression)) return;
        await tester.pump(const Duration(milliseconds: 300));
      }
      await binding.takeScreenshot('ios-map-readiness-timeout');
      final diagnostic = await web.runJavaScriptReturningResult('''JSON.stringify({
        path:location.pathname,
        mapButton:!!document.querySelector('.map-button'),
        price:document.querySelector('[data-testid=current-product-price]')?.textContent,
        body:document.body.innerText.slice(0,1600)
      })''');
      fail('Map condition timed out: $expression; URL=${await web.currentUrl()}; DOM=$diagnostic');
    }
    final path = '/product/limon-tahiti?series=city&presentation=Bulto&units=24+Kilogramo&history=all&region=&market=sipsa-barranquilla-barranquillita';
    await until('document.querySelector(".mobile-nav")');
    final marker = DateTime.now().microsecondsSinceEpoch.toString();
    await web.runJavaScript('window.qaPreviousDocument=${jsonEncode(marker)}');
    await web.loadRequest(Uri.parse('${app.appOrigin}$path'));
    await until('window.qaPreviousDocument!==${jsonEncode(marker)} && location.pathname==="/product/limon-tahiti" && document.querySelector(".map-button") && document.querySelector("[data-testid=current-product-price]")?.textContent.includes("102.500")');
    await web.runJavaScript('document.querySelector(".map-button").click()');
    await until('document.querySelector(".colombia-map")?.dataset.ready==="true"');
    await web.runJavaScript('document.querySelector(".colombia-map").scrollIntoView({block:"center"})');
    await tester.pump(const Duration(seconds: 1));
    final rect = await web.runJavaScriptReturningResult('''JSON.stringify((()=>{const r=document.querySelector('.colombia-map').getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height}})())''');
    debugPrint('IOS_MAP_RECT $rect');
    final initialScroll = await web.runJavaScriptReturningResult('window.scrollY');
    final report = <String, dynamic>{'physical_map_drag': false, 'filtered_map_open': false, 'map_rect': jsonDecode(rect.toString()), 'scroll_before': initialScroll};
    binding.reportData = report;
    await web.runJavaScript('''
      window.qaMapPhysicalMoves=0;
      for(const event of ['touchmove','pointermove'])
        document.querySelector('.colombia-map').addEventListener(event,()=>window.qaMapPhysicalMoves++,{capture:true});
    ''');
    await binding.takeScreenshot('ios-map-before-physical-drag');
    debugPrint('AWAIT_NATIVE_MAP_DRAG swipe within centered map');
    await until('window.qaMapPhysicalMoves>0');
    await tester.pump(const Duration(seconds: 1));
    expect(await ready('location.pathname==="/product/limon-tahiti"'), true);
    expect(await ready('document.querySelector(".map-overlay") && document.querySelector(".colombia-map")?.dataset.ready==="true"'), true);
    expect(await ready('document.documentElement.scrollWidth<=innerWidth'), true);
    final finalScroll = await web.runJavaScriptReturningResult('window.scrollY');
    report['scroll_after'] = finalScroll;
    report['physical_events'] = await web.runJavaScriptReturningResult('window.qaMapPhysicalMoves');
    expect(((finalScroll as num) - (initialScroll as num)).abs() < 5, true);
    report['physical_map_drag'] = true;
    report['filtered_map_open'] = true;
    await binding.takeScreenshot('ios-map-after-physical-drag');
    debugPrint('PASS physical map drag kept filtered map open');
  }, timeout: const Timeout(Duration(minutes: 5)));
}
