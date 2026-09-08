import 'dart:convert';
import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets(
    'Native iOS prices, filters, sources, comparisons and navigation',
    (tester) async {
      app.main();
      await tester.pump(const Duration(seconds: 1));
      final state = tester.state<app.FarmBrowserState>(
        find.byType(app.FarmBrowser),
      );
      final web = state.controller;
      Future<dynamic> js(String code) => web.runJavaScriptReturningResult(code);
      Future<void> until(String condition) async {
        final end = DateTime.now().add(const Duration(seconds: 90));
        while (DateTime.now().isBefore(end)) {
          final value = await js('Boolean($condition)');
          if (value == true || value == 'true') return;
          await tester.pump(const Duration(milliseconds: 300));
        }
        fail(
          'Timed out: $condition; ${await js('document.body.innerText.slice(0,3000)')}',
        );
      }

      Future<void> run(String code) async {
        await web.runJavaScript(code);
        await tester.pump(const Duration(milliseconds: 250));
      }

      Future<void> go(String path, String ready) async {
        final target = Uri.parse('${app.appOrigin}$path');
        final marker = DateTime.now().microsecondsSinceEpoch.toString();
        await web.runJavaScript(
          'window.agroPreviousDocument=${jsonEncode(marker)}',
        );
        await web.loadRequest(target);
        await until(
          'window.agroPreviousDocument!==${jsonEncode(marker)} && location.pathname===${jsonEncode(target.path)} && ($ready)',
        );
        expect(state.failed, false);
        expect(
          await js('document.documentElement.scrollWidth <= innerWidth'),
          true,
        );
      }

      Future<void> click(String selector) async {
        await until('document.querySelector(${jsonEncode(selector)}) !== null');
        await run('document.querySelector(${jsonEncode(selector)}).click()');
      }

      Future<void> select(String selector, String value) async {
        await until(
          '[...document.querySelector(${jsonEncode(selector)})?.options||[]].some(o=>o.value===${jsonEncode(value)})',
        );
        await run(
          '''(()=>{const e=document.querySelector(${jsonEncode(selector)});e.value=${jsonEncode(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()''',
        );
      }

      Future<void> fill(String label, String value) async {
        await run('''(() => {
          const label=[...document.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(${jsonEncode(label)}));
          const field=[...document.querySelectorAll('input')].find(f=>f.getAttribute('aria-label')===${jsonEncode(label)}) || label?.querySelector('input') || (label && document.getElementById(label.htmlFor));
          if(!field)throw Error('Missing field');
          field.focus();
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,${jsonEncode(value)});
          field.dispatchEvent(new Event('input',{bubbles:true}));
        })()''');
      }

      Future<void> shot(String name) async {
        await binding.takeScreenshot('ios-full-$name');
        debugPrint('PASS $name');
      }

      await until('document.querySelector(".mobile-nav")');
      final storage = await js(
        'JSON.stringify(Object.fromEntries(Object.entries(localStorage)))',
      );
      addTearDown(() async {
        await run(
          '''(()=>{const old=JSON.parse(${jsonEncode(storage.toString())});localStorage.clear();for(const [k,v] of Object.entries(old))localStorage.setItem(k,v);})()''',
        );
      });
      await run(
        '''(()=>{const p=JSON.parse(localStorage.getItem("agroamigo-preferences-v2")||"{}");p.region="";localStorage.setItem("agroamigo-preferences-v2",JSON.stringify(p));})()''',
      );
      const price =
          'document.querySelector("[data-testid=current-product-price]")';
      if (!const bool.fromEnvironment('AGRO_IOS_FARM_AND_SOURCES_ONLY')) {
        await go(
          '/product/limon-tahiti?series=city&presentation=Bulto&units=24+Kilogramo',
          '$price?.textContent.includes("86.000")',
        );
        expect(await js('document.body.innerText.includes("Cítricos")'), true);
        expect(
          await js(
            'document.querySelector(".applied-filters").textContent.includes("24 Kilogramo")',
          ),
          true,
        );
        expect(
          await js('document.body.innerText.includes("Calcular transporte")'),
          false,
        );
        await shot('01-filtered-price-classification');
        await click('.chart-data summary');
        expect(
          await js(
            '''(()=>{const p=[...document.querySelectorAll('.chart-data tbody tr td:nth-child(2)')].map(x=>Number(x.textContent.replace(/[^0-9]/g,'')));return p.length>0 && p.every((v,i)=>!i||p[i-1]>=v)})()''',
          ),
          true,
        );
        await shot('02-descending-price-table');
        await click('.map-button');
        await until(
          'document.querySelector(".colombia-map")?.dataset.ready==="true"',
        );
        await select('.map-summary select', 'Atlántico');
        await until(
          'document.querySelector(".map-popup-price")?.textContent.includes("86.000")',
        );
        expect(
          await js(
            'document.querySelector(".map-price-popup").textContent.includes("24 Kilogramo")',
          ),
          true,
        );
        await shot('03-filtered-map-popup');
        await click('button[aria-label="Cerrar ventana"]');
        await until('!document.querySelector("dialog[open]")');
        await run(
          '''[...document.querySelectorAll('a.evidence-link')].find(a=>a.textContent.includes('fuente del precio actual')).click()''',
        );
        await until('document.querySelector(".pdf-paper canvas")?.width>0');
        await shot('04-city-pdf-in-app');
        await click('button[aria-label="Cerrar ventana"]');
        await until('!document.querySelector("dialog[open]")');
        await go(
          '/product/mora-de-castilla?series=city&presentation=Caja+de+cart%C3%B3n&units=2.5+Kilogramo',
          '$price && document.querySelector("select[aria-label=Unidades]")',
        );
        await run(
          '''(()=>{const m=document.querySelector('select[aria-label=Mercado]');const o=[...m.options].find(o=>o.textContent.includes('Barranquillita'));if(!o)throw Error('Missing market');m.value=o.value;m.dispatchEvent(new Event('change',{bubbles:true}));})()''',
        );
        await until('$price?.textContent.includes("21.000")');
        await shot('05-small-package');
        await select('select[aria-label=Unidades]', '12.5 Kilogramo');
        await until('$price?.textContent.includes("79.500")');
        await shot('06-large-package');
        await go(
          '/evidence/2d70e39303ad4dc9337101faa6399d6dbb936f8cb952114db095245c098431e8',
          'document.querySelector(".workbook-scroll tbody tr")',
        );
        await select('select[aria-label="Hoja del archivo Excel"]', '1.3');
        await until(
          'document.querySelector(".workbook-scroll")?.textContent.includes("Fertilizantes")',
        );
        expect(
          await js(
            'document.querySelector(".workbook-viewer").textContent.includes("Solo lectura") && !document.querySelector(".workbook-scroll [contenteditable=true]")',
          ),
          true,
        );
        await shot('07-readonly-excel-sheet');
        await run(
          '''[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Siguientes filas')).click()''',
        );
        await until(
          'document.querySelector(".workbook-scroll tbody th")?.textContent==="101"',
        );
        await shot('08-excel-row-pagination');
        for (final entry in {
          'Productos': '/products',
          'Mercados': '/markets',
          'Insumos': '/insumos',
          'Mi finca': '/farm',
          'Inicio': '/',
        }.entries) {
          await go(
            '/credits',
            'document.querySelector("h1")?.textContent==="Créditos de imágenes"',
          );
          await run(
            '''[...document.querySelectorAll('.mobile-nav a')].find(a=>a.textContent.trim()===${jsonEncode(entry.key)}).click()''',
          );
          await until(
            'location.pathname===${jsonEncode(entry.value)} && document.querySelector("main")?.dataset.section!=="credits"',
          );
          expect(state.failed, false);
          await shot(
            '09-credits-nav-${entry.value.replaceAll('/', '').isEmpty ? 'home' : entry.value.replaceAll('/', '')}',
          );
        }
        await go(
          '/compare/markets?series=city',
          '''document.querySelector('[aria-label="Resultado de la comparación"]')''',
        );
        expect(
          await js(
            'document.querySelector(".applied-filters")?.textContent.includes("Colombia")',
          ),
          true,
        );
        await shot('10-market-national-comparison');
        await go(
          '/compare/inputs?department=Cundinamarca',
          '''document.querySelector('[aria-label="Resultado de la comparación"]')''',
        );
        await shot('11-input-comparison');
        await go(
          '/insumos?scope=municipality',
          'document.querySelector(".input-catalog-card")',
        );
        expect(
          await js(
            'document.querySelector(".applied-filters")?.textContent.includes("Municipio")',
          ),
          true,
        );
        await shot('12-municipal-input-filters');
        await go('/regional?q=Mora', 'document.querySelector(".input-card")');
        await select('select', 'Barranquilla, Barranquillita');
        await until('document.querySelectorAll(".input-card").length>0');
        await click('.input-card h2 a');
        await until(
          '$price && !document.body.innerText.includes("Consultando precios con estos filtros")',
        );
        expect(
          await js(
            'document.querySelector("select[aria-label=Mercado]")?.selectedOptions[0].textContent.includes("Barranquillita")',
          ),
          true,
        );
        await shot('13-regional-market-preserved');
        await go(
          '/references?category=Café',
          'document.querySelector(".official-reference")',
        );
        await select('.price-filter-grid label:nth-child(4) select', 'USD');
        await until(
          '[...document.querySelectorAll(".official-reference")].length>0 && [...document.querySelectorAll(".official-reference")].every(x=>x.textContent.includes("USD"))',
        );
        expect(
          await js(
            'document.querySelector(".official-reference").textContent.includes("USD")',
          ),
          true,
        );
        await shot('14-official-usd-references');
        await click('.official-reference h2 a');
        await until(
          'document.querySelector(".current-product-price")?.textContent.includes("USD")',
        );
        await select('select', 'all');
        await until('document.body.innerText.includes("1960")');
        await click('.chart-data summary');
        await shot('15-international-complete-history');
        expect(
          await js('document.documentElement.scrollWidth<=innerWidth'),
          true,
        );
      }
      await go(
        '/farm',
        '[...document.querySelectorAll("button")].some(e=>e.textContent.trim()==="Usar mi ubicación")',
      );
      // Use the actual CoreLocation path. Before this run set the dedicated
      // simulator to the fixture point, and accept its native location prompt.
      debugPrint(
        'AWAIT_NATIVE_LOCATION_PERMISSION at fixture 1.912345,-76.123456',
      );
      await run(
        "[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Usar mi ubicación').click()",
      );
      await until(
        'document.body.innerText.includes("1.912345") && document.body.innerText.includes("-76.123456")',
      );
      await shot('16-farm-exact-coordinates');
      expect(
        await js(
          'document.querySelector(".location-place").textContent.includes("GPS")',
        ),
        true,
      );
      await go(
        '/farm',
        'document.body.innerText.includes("1.912345") && document.body.innerText.includes("-76.123456")',
      );
      await shot('17-farm-exact-point-restored');
      await go(
        '/data-references?kind=electricity',
        'document.querySelector(".reference-metadata") && document.querySelector("h1")?.textContent.includes("Energía")',
      );
      expect(
        await js(
          'document.querySelector(".applied-filters")?.textContent.includes("Mes")',
        ),
        true,
      );
      await shot('18-electricity-source-data');
      await go(
        '/evidence/9fdcfa8a2aed9a1bb545a10c1a5ce036c6a0acd4766f450424ca800b4b5a0225',
        'document.querySelector(".workbook-scroll tbody tr")',
      );
      await shot('19-international-source-workbook');
      await go(
        '/market/sipsa-armenia-mercar',
        'document.querySelector(".information-tabs")',
      );
      await click('.information-tabs button:last-child');
      await until('document.querySelector(".supply-summary")');
      await until(
        """document.querySelector('[aria-label="Filtros de abastecimiento"] label:last-child select option[value="2019-01-01"]')""",
      );
      await select(
        '[aria-label="Filtros de abastecimiento"] label:last-child select',
        '2019-01-01',
      );
      await until(
        'document.querySelector(".supply-summary") && document.querySelector(".supply-content > .applied-filters")?.textContent.includes("enero de 2019")',
      );
      expect(
        await js('document.documentElement.scrollWidth<=innerWidth'),
        true,
      );
      expect(
        await js(
          'document.querySelector(".supply-bars").scrollWidth>document.querySelector(".supply-bars").clientWidth',
        ),
        true,
      );
      await shot('20-supply-complete-history');
      await until(
        """document.querySelector('[aria-label="Filtros de abastecimiento"] label:last-child select option[value="2020-01-01"]')""",
      );
      await select(
        '[aria-label="Filtros de abastecimiento"] label:last-child select',
        '2020-01-01',
      );
      await until(
        'document.querySelector(".supply-summary") && document.querySelector(".supply-content > .applied-filters")?.textContent.includes("enero de 2020")',
      );
      await shot('21-recovered-2020-supply');
      await go(
        '/farm',
        "document.querySelector('[aria-label=\"Tiempo y pronóstico de mi finca\"]')",
      );
      await until(
        '''document.querySelector('[aria-label="Tiempo y pronóstico de mi finca"]').textContent.includes("estimación del modelo")''',
      );
      await run(
        "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Próximos 7 días').click()",
      );
      await until(
        '''document.querySelectorAll('[aria-label="Tiempo y pronóstico de mi finca"] article').length===7''',
      );
      await run(
        '''document.querySelector('[aria-label="Tiempo y pronóstico de mi finca"]').scrollIntoView({block:"start"})''',
      );
      await shot('22-current-weather-seven-day-forecast');
      await fill('Buscar municipio', 'Pitalito');
      await until(
        '''[...document.querySelectorAll('[role="option"]')].some(o=>o.textContent.toLowerCase().includes("pitalito"))''',
      );
      await run(
        '''[...document.querySelectorAll('[role="option"]')].find(o=>o.textContent.toLowerCase().includes("pitalito")).click()''',
      );
      await click('[role="tab"][aria-controls="clean-panel"]');
      await until(
        '''document.querySelector(".clean-workspace input[type=number]")''',
      );
      await fill('Área que quieres analizar (ha)', '2');
      await fill('Rendimiento esperado (kg/ha)', '1000');
      await fill('Pérdidas antes de vender (%)', '10');
      await run(
        "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Mi precio').click()",
      );
      await fill('Mi precio esperado (COP/kg)', '2000');
      await fill('Labores antes de cosecha (COP/ha)', '200000');
      await fill('Semilla e insumos (COP/ha)', '300000');
      await fill('Mano de obra de cosecha (COP/ha)', '100000');
      await fill('Otros rubros del total publicado (COP/ha)', '0');
      await fill('Transporte, empaque y venta (COP totales)', '100000');
      await fill('Comisión sobre la venta (%)', '10');
      await until(
        '''document.querySelector(".clean-kpis .profit strong")?.textContent.includes("1.940.000")''',
      );
      await run(
        '''document.activeElement.blur();document.querySelector(".clean-results").scrollIntoView({block:"start"})''',
      );
      await shot('23-cleansheet-waterfall-and-profit');
      await run(
        "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Tabla').click()",
      );
      await until(
        '''document.querySelector(".clean-result-table tr.total")?.textContent.includes("1.940.000")''',
      );
      await run(
        '''document.querySelector(".clean-table-wrap").scrollIntoView({block:"start"});document.querySelector(".clean-table-wrap").scrollLeft=260''',
      );
      await shot('24-cleansheet-table');
      await fill('Área que quieres analizar (ha)', '-1');
      await until(
        '''!document.querySelector(".clean-kpis") && document.querySelector(".clean-incomplete")''',
      );
      await go('/', 'document.querySelector(".mobile-nav")');
      debugPrint('PASS native iOS full price/source/navigation suite');
    },
    timeout: const Timeout(Duration(minutes: 25)),
  );
}
