import 'dart:convert';
import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  binding.shouldPropagateDevicePointerEvents = true;
  testWidgets(
    'Simulated iPhone GPS pin saves exact fixture and restores storage',
    (tester) async {
      app.main();
      await tester.pump(const Duration(seconds: 1));
      final state = tester.state<app.FarmBrowserState>(
        find.byType(app.FarmBrowser),
      );
      final web = state.controller;
      Future<dynamic> value(String js) async => jsonDecode(
        (await web.runJavaScriptReturningResult(
          'JSON.stringify(($js) ?? null)',
        )).toString(),
      );
      Future<void> until(String js) async {
        // Simulator automation must respond to both the iOS app and WebKit
        // origin permission sheets before the geolocation callback can fire.
        final deadline = DateTime.now().add(const Duration(minutes: 3));
        while (DateTime.now().isBefore(deadline)) {
          if (await value('Boolean($js)') == true) return;
          await tester.pump(const Duration(milliseconds: 250));
        }
        await binding.takeScreenshot('ios-gps-readiness-timeout');
        final diagnostic = await web.runJavaScriptReturningResult('''JSON.stringify({
          path:location.pathname,
          saved:localStorage.getItem('agroamigo-location-v1'),
          status:[...document.querySelectorAll('[role=status],[role=alert]')].map(e=>e.textContent).slice(0,5),
          body:document.body.innerText.slice(0,1400)
        })''');
        fail('Timed out: $js; URL=${await web.currentUrl()}; DOM=$diagnostic');
      }

      await until('document.querySelector(".mobile-nav")');
      final before =
          await value('Object.fromEntries(Object.entries(localStorage))')
              as Map<String, dynamic>;
      final report = <String, dynamic>{
        'platform': 'IOS',
        'fixture': 'simctl location 4.7110,-74.0721',
        'settings_restored': false,
      };
      binding.reportData = report;
      addTearDown(() async {
        await web.runJavaScript(
          'localStorage.clear();for(const [k,v] of Object.entries(${jsonEncode(before)}))localStorage.setItem(k,v)',
        );
        final after = await value(
          'Object.fromEntries(Object.entries(localStorage))',
        );
        expect(after, before);
        report['settings_restored'] = true;
        binding.reportData = report;
      });
      await web.loadRequest(Uri.parse('${app.appOrigin}/farm'));
      await until('document.querySelector(".location-toolbar button")');
      debugPrint('AWAIT_NATIVE_GPS_TAP exact simulator fixture');
      await until(
        '(()=>{const x=JSON.parse(localStorage.getItem("agroamigo-location-v1")||"null");return x?.method==="gps"&&Math.abs(x.point.latitude-4.7110)<0.0002&&Math.abs(x.point.longitude+74.0721)<0.0002})()',
      );
      final pin =
          await value(
                'JSON.parse(localStorage.getItem("agroamigo-location-v1"))',
              )
              as Map<String, dynamic>;
      expect(pin['method'], 'gps');
      expect(
        await value('document.body.innerText.includes("Pin guardado con GPS")'),
        true,
      );
      report['gps_pin_fixture_matched'] = true;
      report['accuracy_m'] = pin['accuracy'];
      binding.reportData = report;
      await until(
        'document.querySelector(".location-place span")?.textContent.includes("4.711000, -74.072100")',
      );
      await tester.pump(const Duration(seconds: 1));
      await binding.takeScreenshot('ios-simulated-gps-pin');
      debugPrint('PASS simulated GPS exact pin and method');
    },
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
