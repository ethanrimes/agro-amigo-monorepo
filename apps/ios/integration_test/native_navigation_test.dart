import 'package:agroamigo_iphone/main.dart' as app;
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  binding.shouldPropagateDevicePointerEvents = true;
  testWidgets(
    'Real native taps and iOS back swipe',
    (tester) async {
      app.main();
      await tester.pump(const Duration(seconds: 1));
      final state = tester.state<app.FarmBrowserState>(
        find.byType(app.FarmBrowser),
      );
      Future<void> until(String condition) async {
        final end = DateTime.now().add(const Duration(minutes: 5));
        while (DateTime.now().isBefore(end)) {
          if (await state.controller.runJavaScriptReturningResult(
                'Boolean($condition)',
              ) ==
              true) {
            return;
          }
          await tester.pump(const Duration(milliseconds: 250));
        }
        fail(
          'Native action did not reach $condition; URL=${await state.controller.currentUrl()} canGoBack=${await state.controller.canGoBack()}',
        );
      }

      await until('document.querySelector(".home-sections")');
      debugPrint('AWAIT_NATIVE_PRODUCTS tap bottom Productos');
      await until(
        'location.pathname==="/products" && document.querySelector(".product-card")',
      );
      await state.controller.runJavaScript(
        'document.querySelector(".product-card .product-name").scrollIntoView({block:"center"})',
      );
      await binding.takeScreenshot('ios-native-navigation-catalog');
      debugPrint('AWAIT_NATIVE_COFFEE tap first product name');
      await until(
        'location.pathname.startsWith("/product/") && document.querySelector(".coffee-hero,.current-product-price")',
      );
      expect(await state.controller.canGoBack(), true);
      await binding.takeScreenshot('ios-native-navigation-detail');
      debugPrint('AWAIT_NATIVE_SWIPE left edge to right');
      await until(
        'location.pathname==="/products" && document.querySelector(".product-card")',
      );
      await binding.takeScreenshot('ios-native-navigation-back');
      debugPrint('PASS actual native iOS back gesture');
    },
    timeout: const Timeout(Duration(minutes: 20)),
  );
}
