import 'dart:convert';

import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  testWidgets('Installed iOS product photographs decode and paint', (tester) async {
    app.main();
    await tester.pump(const Duration(seconds: 1));
    final web = tester.state<app.FarmBrowserState>(find.byType(app.FarmBrowser)).controller;
    final images = <Map<String, dynamic>>[];
    binding.reportData = {'images': images};
    for (final (slug, label) in [
      ('limon-tahiti', 'limon'),
      ('mora-de-castilla', 'mora'),
      ('papa-criolla-limpia', 'papa'),
    ]) {
      await web.loadRequest(Uri.parse('${app.appOrigin}/product/$slug'));
      final deadline = DateTime.now().add(const Duration(seconds: 35));
      Map<String, dynamic>? result;
      while (DateTime.now().isBefore(deadline)) {
        final raw = await web.runJavaScriptReturningResult('''JSON.stringify((()=>{
          const i=document.querySelector('.detail-picture img');
          const r=i?.getBoundingClientRect();
          return {path:location.pathname,img:!!i,src:i?.currentSrc||i?.src||'',
            complete:i?.complete||false,width:i?.naturalWidth||0,height:i?.naturalHeight||0,
            loading:i?.loading||'',rect:r?{x:r.x,y:r.y,w:r.width,h:r.height}:null,
            visibility:i?getComputedStyle(i).visibility:null,
            opacity:i?getComputedStyle(i).opacity:null,
            pictureText:document.querySelector('.detail-picture')?.textContent||''};
        })())''');
        result = jsonDecode(raw.toString()) as Map<String, dynamic>;
        if (result['path'] == '/product/$slug' && result['img'] == true &&
            (result['width'] as num) > 0) {
          break;
        }
        await tester.pump(const Duration(milliseconds: 250));
      }
      expect(result, isNotNull);
      images.add({'label': label, ...result!});
      debugPrint('IOS_IMAGE ${jsonEncode(images.last)}');
      expect(result['path'], '/product/$slug');
      expect(result['img'], true);
      expect((result['width'] as num) > 0, true);
      await tester.pump(const Duration(seconds: 1));
      await binding.takeScreenshot('ios-image-decoded-$label');
    }
  }, timeout: const Timeout(Duration(minutes: 5)));
}
