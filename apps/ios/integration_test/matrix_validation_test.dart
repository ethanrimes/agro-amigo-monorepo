import 'dart:convert';
import 'dart:io';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

// Shared DOM/data assertions run inside the actual installed WKWebView. Native
// gestures, CoreLocation and sharing remain in the dedicated native suites.
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets(
    'Cross-platform field-level data matrix in WKWebView',
    (tester) async {
      const manifestUrl = String.fromEnvironment('AGRO_QA_MATRIX_URL');
      if (manifestUrl.isEmpty) {
        throw StateError('AGRO_QA_MATRIX_URL is required');
      }
      final uri = Uri.parse(manifestUrl);
      if (!['localhost', '127.0.0.1'].contains(uri.host)) {
        throw StateError(
          'Serve the reviewed QA manifest on host loopback only',
        );
      }
      final client = HttpClient();
      final response = await (await client.getUrl(uri)).close();
      final cases =
          jsonDecode(await utf8.decoder.bind(response).join()) as List;
      client.close();
      app.main();
      await tester.pump(const Duration(seconds: 1));
      final state = tester.state<app.FarmBrowserState>(
        find.byType(app.FarmBrowser),
      );
      final web = state.controller;
      Future<dynamic> value(String expression) async => jsonDecode(
        (await web
                .runJavaScriptReturningResult(
                  'JSON.stringify(($expression) ?? null)',
                )
                .timeout(const Duration(seconds: 25)))
            .toString(),
      );
      Future<void> run(String code) async {
        final asynchronous = code.contains('await ');
        await web
            .runJavaScript(asynchronous
                ? 'window.__qaAction={done:false};void(async()=>{try{$code\nwindow.__qaAction.done=true;}catch(e){window.__qaAction={done:true,error:String(e)}}})()'
                : '(()=>{$code\n})()')
            .timeout(const Duration(seconds: 25));
        if (asynchronous) {
          final deadline = DateTime.now().add(const Duration(seconds: 90));
          while (await value('window.__qaAction?.done') != true) {
            if (DateTime.now().isAfter(deadline)) {
              throw StateError('Asynchronous QA action timed out');
            }
            await tester.pump(const Duration(milliseconds: 100));
          }
          final error = await value('window.__qaAction?.error');
          if (error != null) throw StateError('QA action: $error');
        }
        await tester.pump(const Duration(milliseconds: 150));
      }

      Future<void> ready(String expression) async {
        final deadline = DateTime.now().add(const Duration(seconds: 90));
        Object? lastError;
        while (DateTime.now().isBefore(deadline)) {
          try {
            if (await value('Boolean($expression)') == true) return;
          } catch (error) {
            lastError = error;
          }
          await tester.pump(const Duration(milliseconds: 250));
        }
        throw StateError('Timed out: $expression; last error: $lastError');
      }

      await ready('document.querySelector(".mobile-nav")');
      final original = await value(
        'Object.fromEntries(Object.entries(localStorage))',
      );
      final results = <Map<String, dynamic>>[];
      final report = <String, dynamic>{
        'platform': 'IOS',
        'started_at': DateTime.now().toUtc().toIso8601String(),
        'user_agent': await value('navigator.userAgent'),
        'results': results,
        'settings_restored': false,
      };
      expect(
        (report['user_agent'] as String).contains('AgroAmigoIOS/1.0'),
        true,
      );
      binding.reportData = report;
      addTearDown(() async {
        await run(
          'localStorage.clear();for(const [k,v] of Object.entries(${jsonEncode(original)}))localStorage.setItem(k,v);',
        );
        final restored = await value(
          'Object.fromEntries(Object.entries(localStorage))',
        );
        expect(restored, original);
        report['settings_restored'] = true;
        report['finished_at'] = DateTime.now().toUtc().toIso8601String();
        binding.reportData = report;
      });
      await run(
        'window.qaRelease=null;fetch("/release.json",{cache:"no-store"}).then(r=>r.json()).then(r=>window.qaRelease=r)',
      );
      await ready('window.qaRelease');
      report['release'] = await value('window.qaRelease');
      const expectedRelease = String.fromEnvironment('AGRO_QA_RELEASE');
      if (expectedRelease.isNotEmpty) {
        expect((report['release'] as Map)['id'], expectedRelease);
      }
      for (final raw in cases) {
        final scenario = Map<String, dynamic>.from(raw as Map);
        final name = scenario['name'] as String;
        final result = <String, dynamic>{
          'name': name,
          'route': scenario['route'],
          'checks': <Map<String, dynamic>>[],
        };
        results.add(result);
        try {
          await run(
            'localStorage.clear();for(const [k,v] of Object.entries(${jsonEncode(original)}))localStorage.setItem(k,v);const p=JSON.parse(localStorage.getItem("agroamigo-preferences-v2")||"{}");p.region="";localStorage.setItem("agroamigo-preferences-v2",JSON.stringify(p));',
          );
          final marker = DateTime.now().microsecondsSinceEpoch.toString();
          await run('window.qaPreviousDocument=${jsonEncode(marker)}');
          await web.loadRequest(
            Uri.parse('${app.appOrigin}${scenario['route']}'),
          );
          await ready(
            'window.qaPreviousDocument!==${jsonEncode(marker)} && (${scenario['ready'] ?? 'document.querySelector(".mobile-nav")'})',
          );
          expect(state.failed, false);
          for (final rawStep in scenario['steps'] as List) {
            final step = Map<String, dynamic>.from(rawStep as Map);
            if (step['action'] != null) await run(step['action'] as String);
            if (step['ready'] != null) await ready(step['ready'] as String);
            for (final rawCheck in (step['checks'] ?? []) as List) {
              final check = Map<String, dynamic>.from(rawCheck as Map);
              final outcome = <String, dynamic>{
                'id': check['id'],
                'expected': check['expected'],
              };
              try {
                outcome['passed'] =
                    await value('Boolean(${check['condition']})') == true;
                outcome['observed'] = await value(
                  check['observed'] as String? ?? check['condition'] as String,
                );
              } catch (error) {
                outcome['passed'] = false;
                outcome['error'] = error.toString();
              }
              (result['checks'] as List).add(outcome);
              debugPrint(
                'MATRIX_CHECK ${jsonEncode({'scenario': name, ...outcome})}',
              );
            }
          }
          result['passed'] =
              (result['checks'] as List).isNotEmpty &&
              (result['checks'] as List).every((c) => c['passed'] == true);
        } catch (error) {
          result['passed'] = false;
          result['error'] = error.toString();
          result['body'] = await value('document.body.innerText.slice(0,6000)');
        }
        final screenshot =
            'ios-matrix-${name.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '-')}';
        // WKWebView's DOM can be ready before its native surface is painted.
        // Capture the checked document, not the preceding loading placeholder.
        await run(
          'await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));',
        );
        await tester.pump(const Duration(milliseconds: 500));
        await binding.takeScreenshot(screenshot);
        result['screenshot'] = '$screenshot.png';
        debugPrint('MATRIX_SCENARIO ${jsonEncode(result)}');
        binding.reportData = report;
      }
      await run(
        'window.qaRelease=null;fetch("/release.json",{cache:"no-store"}).then(r=>r.json()).then(r=>window.qaRelease=r)',
      );
      await ready('window.qaRelease');
      report['release_after'] = await value('window.qaRelease');
      expect(
        (report['release_after'] as Map)['id'],
        (report['release'] as Map)['id'],
      );
      expect(results.where((r) => r['passed'] != true).toList(), isEmpty);
    },
    timeout: const Timeout(Duration(minutes: 60)),
  );
}
