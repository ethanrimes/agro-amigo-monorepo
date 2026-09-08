import 'dart:convert';
import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets('Live data, calculations, retry and historical XLS', (
    tester,
  ) async {
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final state = tester.state<app.FarmBrowserState>(
      find.byType(app.FarmBrowser),
    );
    final web = state.controller;
    Future<dynamic> js(String code) => web.runJavaScriptReturningResult(code);
    Future<void> until(String condition) async {
      final deadline = DateTime.now().add(const Duration(seconds: 60));
      while (DateTime.now().isBefore(deadline)) {
        final value = await js('Boolean($condition)');
        if (value == true || value == 'true') return;
        await tester.pump(const Duration(milliseconds: 250));
      }
      fail('Timed out: $condition; ${await js('document.body.innerText')}');
    }

    Future<void> go(String path, String condition) async {
      final target = Uri.parse('${app.appOrigin}$path');
      final marker = DateTime.now().microsecondsSinceEpoch.toString();
      await web.runJavaScript(
        'window.agroPreviousDocument=${jsonEncode(marker)}',
      );
      await web.loadRequest(target);
      await until(
        'window.agroPreviousDocument!==${jsonEncode(marker)} && location.pathname===${jsonEncode(target.path)} && ($condition)',
      );
      expect(
        await js('document.documentElement.scrollWidth <= innerWidth'),
        true,
      );
      expect(state.failed, false);
    }

    Future<void> fill(String label, String value, {bool select = false}) async {
      await web.runJavaScript('''(() => {
    const label=[...document.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(${jsonEncode(label)}));
    const field=[...document.querySelectorAll('input,select,textarea')].find(f=>f.getAttribute('aria-label')===${jsonEncode(label)}) || label?.querySelector('input,select,textarea') || (label && document.getElementById(label.htmlFor));
    if(!field)throw Error('Missing field');
    Object.getOwnPropertyDescriptor(${select ? 'HTMLSelectElement' : 'HTMLInputElement'}.prototype,'value').set.call(field,${jsonEncode(value)});
    field.dispatchEvent(new Event(${jsonEncode(select ? 'change' : 'input')},{bubbles:true}));
   })()''');
      await tester.pump(const Duration(milliseconds: 300));
    }

    await until('document.querySelector(".mobile-nav") !== null');
    final original = await js(
      'JSON.stringify(Object.fromEntries(Object.entries(localStorage)))',
    );
    addTearDown(() async {
      await web.runJavaScript(
        '''(() => {const state=JSON.parse(${jsonEncode(original.toString())});localStorage.clear();for(const [k,v] of Object.entries(state))localStorage.setItem(k,v);})()''',
      );
    });
    await go(
      '/product/cafe-pergamino-seco',
      'document.querySelector(".calculation-result") !== null',
    );
    await fill('Cantidad', '125');
    await fill('Unidad', '1', select: true);
    await fill('Oferta del comprador por carga (COP)', '2100000');
    await fill('Transporte y descuentos totales (COP)', '50000');
    await until(
      'document.querySelector(".calculation-result>strong").textContent.includes("2.050.000")',
    );
    await fill('Cantidad', '10');
    await fill('Unidad', '12.5', select: true);
    await until(
      'document.querySelector(".calculation-result>strong").textContent.includes("2.050.000")',
    );
    await fill('Cantidad', '-1');
    await until('document.querySelector(".invalid-input") !== null');
    expect(
      await js(
        'document.querySelector(".calculation-result>strong").textContent',
      ),
      '—',
    );
    await fill('Cantidad', '10');
    await binding.takeScreenshot('ios-validation-coffee-calculation');
    debugPrint('PASS coffee units, arithmetic and negative-input guard');
    await go('/daily', 'document.querySelectorAll(".input-card").length > 100');
    await web.runJavaScript(
      'fetch("/api/planning/daily").then(r=>r.json()).then(rows=>window.agroValidationDaily=rows)',
    );
    await until('window.agroValidationDaily?.length > 100');
    final day = await js('window.agroValidationDaily[0].observed_on');
    expect(day.toString().compareTo('2026-09-07'), greaterThanOrEqualTo(0));
    expect(
      await js(
        'document.querySelectorAll(".input-card").length === window.agroValidationDaily.length',
      ),
      true,
    );
    await fill('Buscar producto en el boletín', 'Habichuela');
    await until(
      '[...document.querySelectorAll(".input-card")].every(c=>c.textContent.includes("Habichuela")) && document.querySelectorAll(".input-card").length>0',
    );
    await binding.takeScreenshot('ios-validation-daily');
    debugPrint('PASS fresh daily data $day and filtering');
    await go(
      '/offers',
      'document.querySelector("input[aria-label=\\"Precio oferta 1\\"]") !== null',
    );
    await fill('Cantidad total que comparas (kg)', '250');
    await fill('Unidad de las cotizaciones', '125', select: true);
    await fill('Precio oferta 1', '2000000');
    await fill('Kilos oferta 1', '250');
    await fill('Descuento oferta 1', '5');
    await fill('Transporte oferta 1', '100000');
    await until(
      'document.querySelector(".offer-result strong").textContent.includes("3.700.000")',
    );
    await web.reload();
    await until(
      'document.querySelector(".offer-result strong")?.textContent.includes("3.700.000")',
    );
    await binding.takeScreenshot('ios-validation-offers');
    debugPrint('PASS offers: units, discount, transport and persistence');
    await go(
      '/products',
      'document.querySelectorAll(".product-card").length > 0',
    );
    await web.runJavaScript(
      '''window.agroRealFetch=window.fetch;window.fetch=(...args)=>String(args[0]).includes('/api/catalog')?Promise.resolve(new Response(JSON.stringify({error:'Simulator validation'}),{status:503,headers:{'Content-Type':'application/json'}})):window.agroRealFetch(...args);''',
    );
    await fill('Departamento', 'Antioquia', select: true);
    await until('document.querySelector("main [role=alert]") !== null');
    await binding.takeScreenshot('ios-validation-data-error');
    await web.runJavaScript(
      '''window.fetch=window.agroRealFetch;[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Volver a intentar').click()''',
    );
    await until('document.querySelectorAll(".product-card").length > 0');
    debugPrint('PASS data error, retry and recovery');
    await go(
      '/insumos',
      'document.querySelector(".input-catalog-card") !== null',
    );
    await binding.takeScreenshot('ios-validation-inputs');
    await go(
      '/evidence/daily-2012-06-12-workbook',
      'document.body.innerText.includes("Descargar archivo")',
    );
    expect(await js('document.body.innerText.includes("2012")'), true);
    await web.runJavaScript(
      '''[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='Descargar archivo').click()''',
    );
    final deadline = DateTime.now().add(const Duration(seconds: 45));
    while (!state.sharing && DateTime.now().isBefore(deadline)) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    expect(state.sharing, true);
    await tester.pump(const Duration(seconds: 3));
    expect(state.failed, false);
    await binding.takeScreenshot('ios-validation-historical-xls-share');
    debugPrint('PASS historical 2012 XLS native sharing');
  });
}
