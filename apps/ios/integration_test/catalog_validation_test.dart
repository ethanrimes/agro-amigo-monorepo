import 'dart:convert';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

// Runs against the real WKWebView and deployed site. DOM geometry and retained
// screenshots provide separate evidence: geometry cannot detect stale GPU paint.
const _geometry = r'''(() => {
  const cards = [...document.querySelectorAll('.product-grid > .product-card')];
  const errors = [], visible = [], tolerance = 2;
  const rect = e => e.getBoundingClientRect();
  const inside = (a, b) => a.left >= b.left - tolerance && a.right <= b.right + tolerance &&
    a.top >= b.top - tolerance && a.bottom <= b.bottom + tolerance;
  const overlap = (a, b) => Math.min(a.right,b.right)-Math.max(a.left,b.left)>tolerance &&
    Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>tolerance;
  const navTop = document.querySelector('.mobile-nav')?.getBoundingClientRect().top || innerHeight;
  cards.forEach((card, i) => {
    const bounds = rect(card), name = card.querySelector('.product-name')?.textContent.trim();
    const body = card.querySelector('.product-card-body'), image = card.querySelector('.product-image-link');
    if (!body || !image) { errors.push(`${i}: missing card structure`); return; }
    const parts = ['.product-name','.product-date','.product-price','.price-change,.no-change','.product-card-footer']
      .map(selector => body.querySelector(selector));
    if (parts.some(e => !e)) { errors.push(`${i}: missing body field`); return; }
    for (const e of [body,image,...parts]) {
      const b = rect(e);
      if (!b.width || !b.height || !inside(b,bounds)) errors.push(`${i} ${name}: ${e.className} escapes card`);
    }
    if (rect(image).bottom > rect(body).top+tolerance) errors.push(`${i}: image/body overlap`);
    parts.forEach((e,j) => {
      if (!inside(rect(e),rect(body))) errors.push(`${i}: ${e.className} escapes body`);
      if (j && rect(parts[j-1]).bottom > rect(e).top+tolerance) errors.push(`${i}: adjacent body fields overlap`);
      // Text ranges detect long prices/units. Honor intentional name ellipsis.
      const range = document.createRange(); range.selectNodeContents(e);
      for (const line of range.getClientRects()) {
        const style=getComputedStyle(e), own=rect(e);
        const visibleLine={left:line.left,right:line.right,top:line.top,bottom:line.bottom};
        if(['hidden','clip'].includes(style.overflowX)) {
          visibleLine.left=Math.max(visibleLine.left,own.left);visibleLine.right=Math.min(visibleLine.right,own.right);
        }
        if(['hidden','clip'].includes(style.overflowY)) {
          visibleLine.top=Math.max(visibleLine.top,own.top);visibleLine.bottom=Math.min(visibleLine.bottom,own.bottom);
        }
        if(line.width&&line.height&&!inside(visibleLine,bounds)) errors.push(`${i}: ${e.className} text escapes card`);
      }
    });
    if (Math.min(bounds.bottom,navTop-5)-Math.max(bounds.top,100)>40) {
      visible.push({index:i,name,loaded:[...image.querySelectorAll('img')].every(e=>e.complete&&e.naturalWidth>0)});
      // Sample hit testing below the fixed header and above the bottom nav.
      const x=(bounds.left+bounds.right)/2, y=(Math.max(bounds.top,150)+Math.min(bounds.bottom,navTop-10))/2;
      if (y>150 && y<navTop-10 && document.elementFromPoint(x,y)?.closest('.product-card')!==card)
        errors.push(`${i}: visible card covered by another DOM element`);
    }
    for (let j=0;j<i;j++) if(overlap(bounds,rect(cards[j]))) errors.push(`${j}/${i}: neighboring cards overlap`);
  });
  if(document.documentElement.scrollWidth>innerWidth+1) errors.push('page overflows viewport');
  return JSON.stringify({errors,visible,count:cards.length,scrollY});
})()''';

const _supplyWidth = r'''(() => {
  const grid=document.querySelector('.supply-filter-grid'), errors=[];
  if(!grid) return JSON.stringify(['missing supply-filter-grid']);
  const style=getComputedStyle(grid), box=grid.getBoundingClientRect();
  const left=box.left+parseFloat(style.borderLeftWidth)+parseFloat(style.paddingLeft);
  const right=box.right-parseFloat(style.borderRightWidth)-parseFloat(style.paddingRight);
  const fields=[...grid.querySelectorAll('.form-field')];
  if(fields.length!==1) errors.push('expected one full-width month selector');
  fields.forEach((field,i)=>{
    const label=field.getBoundingClientRect(), select=field.querySelector('select').getBoundingClientRect();
    if(Math.abs(label.left-left)>2||Math.abs(label.right-right)>2) errors.push(`${i}: label is not full width`);
    if(Math.abs(select.left-left)>2||Math.abs(select.right-right)>2) errors.push(`${i}: select is not full width`);
    if(i&&fields[i-1].getBoundingClientRect().bottom>label.top+2) errors.push('filter controls overlap');
  });
  if(document.documentElement.scrollWidth>innerWidth+1) errors.push('supply page overflows');
  return JSON.stringify(errors);
})()''';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  binding.shouldPropagateDevicePointerEvents =
      const bool.fromEnvironment('NATIVE_CATALOG_GESTURES');
  testWidgets(
    'iOS catalog scrolling and retained supply months',
    (tester) async {
      app.main();
      await tester.pump(const Duration(seconds: 1));
      final state = tester.state<app.FarmBrowserState>(
        find.byType(app.FarmBrowser),
      );
      final web = state.controller;
      Future<dynamic> js(String code) => web
          .runJavaScriptReturningResult(code)
          .timeout(const Duration(seconds: 20));
      Future<dynamic> json(String code) async =>
          jsonDecode((await js(code)).toString());
      Future<void> run(String code) async {
        await web.runJavaScript(code);
        await tester.pump(const Duration(milliseconds: 300));
      }

      Future<void> until(String condition) async {
        final deadline = DateTime.now().add(const Duration(seconds: 90));
        while (DateTime.now().isBefore(deadline)) {
          final value = await js('Boolean($condition)');
          if (value == true || value == 'true') return;
          await tester.pump(const Duration(milliseconds: 300));
        }
        fail(
          'Timed out: $condition; ${await js('document.body.innerText.slice(0,2500)')}',
        );
      }

      Future<void> go(String path, String ready) async {
        final marker = DateTime.now().microsecondsSinceEpoch.toString();
        await run('window.agroCatalogPreviousDocument=${jsonEncode(marker)}');
        await web.loadRequest(Uri.parse('${app.appOrigin}$path'));
        await until(
          'window.agroCatalogPreviousDocument!==${jsonEncode(marker)} && location.pathname===${jsonEncode(Uri.parse(path).path)} && ($ready)',
        );
        expect(state.failed, false);
      }

      Future<void> click(String selector) async {
        await until('document.querySelector(${jsonEncode(selector)})');
        await run('document.querySelector(${jsonEncode(selector)}).click()');
      }

      Future<void> select(String selector, String value) async {
        await until(
          'document.querySelector(${jsonEncode(selector)}) && !document.querySelector(${jsonEncode(selector)}).disabled',
        );
        await run(
          '''(()=>{const e=document.querySelector(${jsonEncode(selector)});if(![...e.options].some(o=>o.value===${jsonEncode(value)}))throw Error('Missing option');e.value=${jsonEncode(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()''',
        );
      }

      Future<void> shot(String name) async {
        await binding.takeScreenshot('ios-catalog-$name');
        debugPrint('CAPTURE ios-catalog-$name (visual review required)');
      }

      await until('document.querySelector(".mobile-nav")');
      final originalStorage = await json(
        'JSON.stringify(Object.fromEntries(Object.entries(localStorage)))',
      );
      addTearDown(() async {
        // Restore every original value exactly, including saved-item ordering.
        await run(
          '''(()=>{const old=${jsonEncode(originalStorage)};localStorage.clear();for(const [k,v]of Object.entries(old))localStorage.setItem(k,v);})()''',
        );
        expect(
          await json(
            'JSON.stringify(Object.fromEntries(Object.entries(localStorage)))',
          ),
          originalStorage,
        );
      });
      await run(
        '''(()=>{const p=JSON.parse(localStorage.getItem('agroamigo-preferences-v2')||'{}');p.region='';localStorage.setItem('agroamigo-preferences-v2',JSON.stringify(p));})()''',
      );
      const cards =
          'document.querySelectorAll(".product-grid > .product-card")';
      await go('/products', '$cards.length===24');
      final initial = await json(
        'JSON.stringify([...$cards].map(e=>({href:e.querySelector(".product-name").getAttribute("href"),text:e.querySelector(".product-card-body").textContent})))',
      );
      final sweepEvidence = <Map<String, dynamic>>[];
      Future<void> sweep(bool down) async {
        final seen = <int>{};
        await run(
          '''(()=>{const c=[...$cards].slice(0,24);window.scrollTo(0,${down ? 'c[0].getBoundingClientRect().top+scrollY-110' : 'c[23].getBoundingClientRect().bottom+scrollY-innerHeight+160'});})()''',
        );
        for (var step = 0; step < 90 && seen.length < 24; step++) {
          await until('JSON.parse($_geometry).visible.every(e=>e.loaded)');
          final check = Map<String, dynamic>.from(await json(_geometry) as Map);
          expect(
            check['errors'],
            isEmpty,
            reason: '${down ? "down" : "up"} step $step: $check',
          );
          for (final v in check['visible'] as List) {
            if ((v['index'] as int) < 24) seen.add(v['index'] as int);
          }
          sweepEvidence.add({
            'direction': down ? 'down' : 'up',
            'step': step,
            ...check,
          });
          if (step == 0 || step == 8 || seen.length == 24) {
            await shot('${down ? "down" : "up"}-$step');
          }
          if (seen.length == 24) break;
          final before = check['scrollY'] as num;
          // Scroll the actual WKWebView document in overlapping viewport steps.
          // This is a browser scroll regression, not an injected native-swipe test.
          await run(
            'window.scrollBy(0,innerHeight*${down ? '0.55' : '-0.55'})',
          );
          final after = await js('scrollY') as num;
          expect(
            down ? after > before : after < before,
            true,
            reason: 'Scroll stalled after ${seen.length}/24 cards',
          );
        }
        expect(
          seen.length,
          24,
          reason:
              'Every initial card must enter the viewport in both directions',
        );
      }

      await sweep(true);
      await sweep(false);
      debugPrint('CATALOG_SCROLL_GEOMETRY ${jsonEncode(sweepEvidence)}');
      await click('.load-more button');
      await until('$cards.length>24');
      expect(
        await json(
          'JSON.stringify([...$cards].slice(0,24).map(e=>({href:e.querySelector(".product-name").getAttribute("href"),text:e.querySelector(".product-card-body").textContent})))',
        ),
        initial,
      );
      expect((await json(_geometry))['errors'], isEmpty);
      await shot('load-more-preserved-cards');

      for (final target in ['cafe-pergamino-seco', 'tomate']) {
        final selector =
            '.product-card:has(.product-name[href*="/product/$target"])';
        await until('document.querySelector(${jsonEncode(selector)})');
        for (final offset in [130, 300]) {
          await run(
            '''(()=>{const e=document.querySelector(${jsonEncode(selector)});scrollTo(0,e.getBoundingClientRect().top+scrollY-$offset);})()''',
          );
          await until('JSON.parse($_geometry).visible.every(e=>e.loaded)');
          expect((await json(_geometry))['errors'], isEmpty);
          await shot('$target-offset-$offset');
        }
      }

      const coffee =
          '.product-card:has(.product-name[href*="/product/cafe-pergamino-seco"])';
      final prefs = await js(
        'localStorage.getItem("agroamigo-preferences-v2")',
      );
      final wasSaved = await js(
        'document.querySelector(\'$coffee .save-button\').getAttribute("aria-pressed")==="true"',
      );
      await click('$coffee .save-button');
      await until(
        'document.querySelector(\'$coffee .save-button\').getAttribute("aria-pressed")==="${wasSaved == true ? 'false' : 'true'}" && JSON.parse(localStorage.getItem("agroamigo-preferences-v2")).saved.includes("cafe-pergamino-seco")===${wasSaved == true ? 'false' : 'true'}',
      );
      await shot('coffee-save-toggled');
      await run(
        'localStorage.setItem("agroamigo-preferences-v2",${jsonEncode(prefs)})',
      );
      await go('/products', '$cards.length===24');
      await until(
        'document.querySelector(\'$coffee .save-button\').getAttribute("aria-pressed")==="${wasSaved == true ? 'true' : 'false'}"',
      );
      const nativeGestures = bool.fromEnvironment('NATIVE_CATALOG_GESTURES');
      if (nativeGestures) {
        await run(
          'document.querySelector(\'$coffee .product-name\').scrollIntoView({block:"center"})',
        );
        debugPrint('AWAIT_NATIVE_TAP coffee product name');
      } else {
        await click('$coffee .product-name');
      }
      await until(
        'location.pathname==="/product/cafe-pergamino-seco" && !document.querySelector(".catalog-heading") && document.querySelector("h1")',
      );
      expect(state.failed, false);
      await shot('coffee-detail');
      expect(await web.canGoBack(), true);
      if (nativeGestures) {
        debugPrint('AWAIT_NATIVE_BACK left-edge swipe');
      } else {
        // Synthetic JS clicks do not create user-activated WKWebView history
        // entries. Exercise the visible back link here; the optional native
        // mode uses a real simulator tap and edge swipe for browser history.
        await click('.back-link');
      }
      await until('location.pathname==="/products" && $cards.length===24');
      expect((await json(_geometry))['errors'], isEmpty);
      expect(
        await js('localStorage.getItem("agroamigo-preferences-v2")'),
        prefs,
      );
      await shot('catalog-after-detail-back');

      await go(
        '/products?q=cafe&category=Caf%C3%A9&currency=USD',
        '$cards.length>0 && [...$cards].every(e=>e.querySelector(".product-price")?.dataset.currency==="USD")',
      );
      expect(
        await js('document.querySelector("select[aria-label=Moneda]").value'),
        'USD',
      );
      expect(
        await js(
          'document.querySelector(".applied-filters").textContent.includes("cafe")',
        ),
        true,
      );
      expect(
        await js(
          r'''[...document.querySelectorAll('main a')].filter(a=>['/references','/regional','/data-references'].includes(a.pathname)).length''',
        ),
        0,
      );
      expect((await json(_geometry))['errors'], isEmpty);
      await shot('unified-coffee-usd-results');
      final quote = await json(
        r'''JSON.stringify((()=>{const c=document.querySelector('.product-card'),p=c.querySelector('.product-price');return {price:Number(p.dataset.price),currency:p.dataset.currency,key:c.dataset.productId,returnTo:location.pathname+location.search};})())''',
      );
      await click('.product-card .product-name');
      await until(
        'location.pathname.startsWith("/references/") && document.querySelector(".current-product-price")?.dataset.currency==="USD"',
      );
      expect(
        await js(
          'Number(document.querySelector(".current-product-price").dataset.price)',
        ),
        quote['price'],
      );
      expect(
        await js('document.querySelector(".back-link").getAttribute("href")'),
        quote['returnTo'],
      );
      if (await js(
            'document.querySelector(".detail-save").getAttribute("aria-pressed")==="false"',
          ) ==
          true) {
        await click('.detail-save');
      }
      expect(
        await js(
          'JSON.parse(localStorage.getItem("agroamigo-preferences-v2")).saved.includes(${jsonEncode(quote['key'])})',
        ),
        true,
      );
      await select('.chart-panel select', 'all');
      await until(
        'document.querySelector(".chart-panel").textContent.includes("1960")',
      );
      await click('.chart-data summary');
      expect(
        await js(
          'document.querySelectorAll(".chart-data tbody tr").length>=800',
        ),
        true,
      );
      await shot('unified-reference-complete-history');
      await click('.back-link');
      await until(
        'location.pathname==="/products" && $cards.length>0 && document.querySelector("select[aria-label=Moneda]")?.value==="USD"',
      );
      expect(
        await js(
          'document.querySelector(".applied-filters").textContent.includes("cafe")',
        ),
        true,
      );
      await go('/saved?q=cafe&currency=USD', '$cards.length>0');
      expect(
        await js(
          '[...$cards].some(e=>e.dataset.productId===${jsonEncode(quote['key'])})',
        ),
        true,
      );
      await shot('unified-reference-saved');
      await go(
        '/products?q=rosas&category=Flores&currency=USD',
        '$cards.length>0 && [...$cards].every(e=>e.querySelector(".product-price")?.dataset.currency==="USD")',
      );
      expect((await json(_geometry))['errors'], isEmpty);
      await shot('unified-roses-results');
      debugPrint(
        'PASS unified catalog currency, exact quote, 1960 history, saved identity, return filters and roses search',
      );

      await go(
        '/market/sipsa-armenia-mercar',
        'document.querySelector(".information-tabs")',
      );
      await run(
        r'''window.agroCatalogSupplyFetch=window.fetch;window.fetch=async function(...args){
      const response=await window.agroCatalogSupplyFetch.apply(this,args);
      if(String(args[0]).includes('/api/explore/supply'))response.clone().json().then(data=>{
        window.agroCatalogSupply={url:String(args[0]),status:response.status,selected:data.selected_period,
          rows:data.rows?.length,periods:[...new Set((data.rows||[]).map(r=>r.period_start))],
          total:(data.rows||[]).reduce((n,r)=>n+r.quantity_kg,0)};
      });return response;
    };''',
      );
      await click('.information-tabs button:last-child');
      await until('document.querySelector(".supply-summary")');
      expect(
        await js('innerWidth<=600'),
        true,
        reason: 'Run on a portrait phone simulator',
      );
      expect(await json(_supplyWidth), isEmpty);
      const month = '.supply-filter-grid label:last-child select';
      await until(
        'document.querySelector(\'$month option[value="2020-12-01"]\') && !document.querySelector(\'$month\').disabled',
      );
      final expected = [
        for (final year in [2019, 2020])
          for (var m = 1; m <= 12; m++)
            '$year-${m.toString().padLeft(2, '0')}-01',
      ];
      final available =
          await json(
                'JSON.stringify([...document.querySelector(\'$month\').options].map(o=>o.value))',
              )
              as List;
      expect(
        available.toSet().length,
        available.length,
        reason: 'Month options must be unique',
      );
      expect(available, containsAll(expected));
      final monthEvidence = <dynamic>[];
      for (final date in expected) {
        await select(month, date);
        await until(
          '''window.agroCatalogSupply?.status===200 && window.agroCatalogSupply.selected===${jsonEncode(date)} && document.querySelector('.supply-summary') && !document.querySelector('$month').disabled && document.querySelector('.supply-content > .applied-filters')?.textContent.includes(new Date('${date}T12:00:00Z').toLocaleDateString('es-CO',{month:'long',year:'numeric',timeZone:'America/Bogota'}))''',
        );
        final result = await json('JSON.stringify(window.agroCatalogSupply)');
        expect(result['periods'], [date]);
        expect(result['rows'], greaterThan(0));
        expect(result['total'], greaterThan(0));
        expect(
          Uri.parse(result['url'] as String).queryParameters['history'],
          'all',
        );
        expect(
          Uri.parse(result['url'] as String).queryParameters['month'],
          date,
        );
        expect(await json(_supplyWidth), isEmpty, reason: date);
        expect(
          await js(
            'document.querySelector(".supply-content > .applied-filters").textContent.includes("DANE SIPSA-A")',
          ),
          true,
        );
        monthEvidence.add(result);
        if (date.endsWith('-01-01') || date.endsWith('-12-01')) {
          await run(
            'document.querySelector(".supply-filter-grid").scrollIntoView({block:"center"})',
          );
          await shot('supply-$date-full-width');
        }
      }
      debugPrint('SUPPLY_MONTH_VALIDATION ${jsonEncode(monthEvidence)}');
      await go('/', 'document.querySelector(".mobile-nav")');
      debugPrint(
        'PASS catalog geometry/navigation/save and all 24 supply months; inspect captured images separately for paint artifacts',
      );
    },
    timeout: const Timeout(Duration(minutes: 20)),
  );
}
