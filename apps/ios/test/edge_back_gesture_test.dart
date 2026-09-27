import 'package:agroamigo_iphone/edge_back_gesture.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('completed left edge drag goes back exactly once', (
    tester,
  ) async {
    var backs = 0;
    await tester.pumpWidget(
      EdgeBackGesture(
        enabled: true,
        onBack: () => backs++,
        child: const SizedBox.expand(),
      ),
    );
    await tester.dragFrom(const Offset(4, 200), const Offset(200, 0));
    expect(backs, 1);
  });

  testWidgets(
    'non-edge drags, vertical scrolling and a cancelled swipe keep the page',
    (tester) async {
      var backs = 0, verticals = 0;
      await tester.pumpWidget(
        EdgeBackGesture(
          enabled: true,
          onBack: () => backs++,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onVerticalDragUpdate: (_) => verticals++,
            child: const SizedBox.expand(),
          ),
        ),
      );
      await tester.dragFrom(const Offset(100, 200), const Offset(200, 0));
      await tester.dragFrom(const Offset(4, 200), const Offset(0, 200));
      final touch = await tester.startGesture(const Offset(4, 200));
      await touch.moveBy(const Offset(50, 0));
      await touch.cancel();
      expect(backs, 0);
      expect(verticals, greaterThan(0));
    },
  );

  testWidgets('no back gesture when there is no previous page', (tester) async {
    var backs = 0;
    await tester.pumpWidget(
      EdgeBackGesture(
        enabled: false,
        onBack: () => backs++,
        child: const SizedBox.expand(),
      ),
    );
    await tester.dragFrom(const Offset(4, 200), const Offset(200, 0));
    expect(backs, 0);
  });
}
