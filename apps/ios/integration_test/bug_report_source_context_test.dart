import 'dart:convert';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets('Source viewer bug form keeps safe context without private location', (tester) async {
    const documentId = '21059d452c382cc9f3b057c686ba904e7d277f624b2c948f3dd1e73def917042';
    const path = '/evidence/$documentId?page=1';
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final web = tester.state<app.FarmBrowserState>(find.byType(app.FarmBrowser)).controller;
    Future<dynamic> value(String expression) async => jsonDecode(
      (await web.runJavaScriptReturningResult('JSON.stringify(($expression) ?? null)')).toString(),
    );
    Future<void> ready(String expression) async {
      final end = DateTime.now().add(const Duration(seconds: 90));
      while (DateTime.now().isBefore(end)) {
        if (await value('Boolean($expression)') == true) return;
        await tester.pump(const Duration(milliseconds: 250));
      }
      fail('Timed out: $expression URL=${await web.currentUrl()}');
    }
    await ready('document.querySelector(".mobile-nav")');
    final storage = await value('Object.fromEntries(Object.entries(localStorage))');
    final report = <String, dynamic>{'source_document_id': documentId, 'real_post_sent': false, 'settings_restored': false};
    binding.reportData = report;
    addTearDown(() async {
      await web.runJavaScript('localStorage.clear();for(const [k,v] of Object.entries(${jsonEncode(storage)}))localStorage.setItem(k,v)');
      expect(await value('Object.fromEntries(Object.entries(localStorage))'), storage);
      report['settings_restored'] = true;
      binding.reportData = report;
    });
    await web.runJavaScript('localStorage.setItem("agroamigo-location-v1",${jsonEncode('{"point":{"latitude":1.912345,"longitude":-74.987654},"method":"manual"}')})');
    await web.loadRequest(Uri.parse('${app.appOrigin}$path'));
    await ready('location.pathname==="/evidence/$documentId" && document.querySelector("a[href*=\\"/reportar?from=\\"]")');
    await web.runJavaScript('document.querySelector(\'a[href*="/reportar?from="]\').click()');
    await ready('location.pathname==="/reportar" && document.querySelector("#bug-message")');
    // Install the stub in this document. Evidence -> report may be a full
    // WKWebView navigation, which discards overrides from the evidence page.
    await web.runJavaScript('''
      window.__bugReportCalls=[];
      const originalFetch=window.fetch.bind(window);
      window.fetch=(input,init)=>{
        const path=new URL(typeof input==='string'?input:input.url,location.href).pathname;
        if(path==='/api/bug-reports'){
          window.__bugReportCalls.push(JSON.parse(init.body));
          return Promise.resolve(new Response(JSON.stringify({id:'ios-source-stub',status:'queued'}),{status:201,headers:{'Content-Type':'application/json'}}));
        }
        return originalFetch(input,init);
      };
    ''');
    expect(await value('Array.isArray(window.__bugReportCalls)'), true);
    expect(await value('window.fetch.toString().includes("__bugReportCalls")'), true);
    expect(await value('document.body.innerText.includes("Fuente consultada · página 1")'), true);
    expect(await value('document.body.innerText.includes("$documentId")'), false);
    expect(await value('document.querySelector(".mobile-nav") !== null'), true);
    await binding.takeScreenshot('ios-bug-source-context');
    await web.runJavaScript('''
      const message=document.querySelector('#bug-message');
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(message,'La página del PDF se ve mal en iPhone.');
      message.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('#bug-consent').click();
    ''');
    await ready('document.querySelector("#bug-consent").checked && document.querySelector("#bug-message").value.length>=10');
    await web.runJavaScript('document.querySelector("button[type=submit]").click()');
    await ready('document.querySelector("[role=status]")?.textContent.includes("Reporte en cola")');
    final calls = await value('window.__bugReportCalls') as List;
    expect(calls.length, 1);
    final body = Map<String, dynamic>.from(calls.single as Map);
    expect(body['page_path'], path);
    expect(body['source_document_id'], documentId);
    expect(body['consent'], true);
    expect(body.containsKey('reply_email'), false);
    expect(body.toString().contains('1.912345'), false);
    expect(body.toString().contains('-74.987654'), false);
    report['stubbed_post_count'] = 1;
    report['human_context_label'] = 'Fuente consultada · página 1';
    report['safe_page_path'] = path;
    debugPrint('IOS_BUG_SOURCE_CONTEXT safe page path, source id, local stub only');
  }, timeout: const Timeout(Duration(minutes: 5)));
}
