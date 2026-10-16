import 'dart:convert';
import 'dart:io';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets('Installed iOS bug report uses a local submission stub', (tester) async {
    const expectedRelease = String.fromEnvironment('AGRO_QA_RELEASE');
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final state = tester.state<app.FarmBrowserState>(find.byType(app.FarmBrowser));
    final web = state.controller;
    Future<dynamic> value(String expression) async => jsonDecode(
      (await web.runJavaScriptReturningResult('JSON.stringify(($expression) ?? null)')).toString(),
    );
    Future<void> run(String code) async {
      await web.runJavaScript('(()=>{$code})()');
      await tester.pump(const Duration(milliseconds: 200));
    }
    Future<void> ready(String expression) async {
      final end = DateTime.now().add(const Duration(seconds: 60));
      while (DateTime.now().isBefore(end)) {
        if (await value('Boolean($expression)') == true) return;
        await tester.pump(const Duration(milliseconds: 250));
      }
      fail('Timed out: $expression');
    }

    await ready('document.querySelector(".mobile-nav")');
    final storage = await value('Object.fromEntries(Object.entries(localStorage))');
    final report = <String, dynamic>{'platform': 'IOS', 'settings_restored': false};
    binding.reportData = report;
    addTearDown(() async {
      await run('localStorage.clear();for(const [k,v] of Object.entries(${jsonEncode(storage)}))localStorage.setItem(k,v);');
      expect(await value('Object.fromEntries(Object.entries(localStorage))'), storage);
      report['settings_restored'] = true;
      report['finished_at'] = DateTime.now().toUtc().toIso8601String();
      binding.reportData = report;
      final target = Platform.environment['AGRO_IOS_TEST_ARTIFACTS'];
      if (target != null) {
        final dir = Directory(target);
        await dir.create(recursive: true);
        await File('${dir.path}/report.json').writeAsString('${const JsonEncoder.withIndent('  ').convert(report)}\n');
      }
    });

    await run('window.__qaRelease=null;fetch("/release.json",{cache:"no-store"}).then(r=>r.json()).then(r=>window.__qaRelease=r)');
    await ready('window.__qaRelease');
    report['release_before'] = await value('window.__qaRelease.id');
    expect(report['release_before'], expectedRelease);

    await run('document.querySelector(\'header a[aria-label="Reportar un problema"]\').click();');
    await ready('location.pathname==="/reportar" && document.querySelector("#bug-message")');
    // A full WKWebView navigation discards earlier overrides. Install the stub
    // in the actual form document, immediately before the only submit action.
    await run('''
      window.__bugReportCalls=[];
      const originalFetch=window.fetch.bind(window);
      window.fetch=(input,init)=>{
        const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
        if(path==='/api/bug-reports'){
          window.__bugReportCalls.push(JSON.parse(init.body));
          return Promise.resolve(new Response(JSON.stringify({id:'ios-local-stub',status:'queued'}),{status:201,headers:{'Content-Type':'application/json'}}));
        }
        return originalFetch(input,init);
      };
    ''');
    expect(await value('window.fetch.toString().includes("__bugReportCalls")'), true);
    expect(await value('document.querySelector(".mobile-nav") !== null'), true);
    expect(await value('document.body.innerText.includes("Correo para responderte (opcional)")'), true);
    await run('''
      const message=document.querySelector('#bug-message');
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(message,'En iPhone el dato de prueba no abrió su fuente.');
      message.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('#bug-consent').click();
    ''');
    await ready('document.querySelector("#bug-message").value.length>=10 && document.querySelector("#bug-consent").checked');
    await run('document.querySelector("button[type=submit]").click();');
    await ready('document.querySelector("[role=status]")?.textContent.includes("Reporte en cola")');
    final calls = await value('window.__bugReportCalls');
    expect((calls as List).length, 1);
    final body = Map<String, dynamic>.from(calls.single as Map);
    expect(body['message'], 'En iPhone el dato de prueba no abrió su fuente.');
    expect(body['consent'], true);
    expect(body['page_path'], '/');
    expect(body.containsKey('reply_email'), false);
    expect(body.containsKey('source_document_id'), false);
    expect(body.toString().contains('1.912345'), false);
    expect(await value('document.querySelector("[role=status]").textContent.includes("no confirma que el correo ya haya llegado")'), true);
    report['stubbed_post_count'] = calls.length;
    report['queued_confirmation'] = true;
    report['real_post_sent'] = false;
    await run('window.__qaReleaseAfter=null;fetch("/release.json",{cache:"no-store"}).then(r=>r.json()).then(r=>window.__qaReleaseAfter=r)');
    await ready('window.__qaReleaseAfter');
    report['release_after'] = await value('window.__qaReleaseAfter.id');
    expect(report['release_after'], expectedRelease);
    debugPrint('IOS_BUG_REPORT ${jsonEncode(report)}');
  });
}
