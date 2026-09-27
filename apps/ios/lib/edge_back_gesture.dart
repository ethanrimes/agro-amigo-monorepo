import 'package:flutter/gestures.dart';
import 'package:flutter/widgets.dart';

// Participate only at the left screen edge. Other horizontal gestures (maps,
// source tables) and vertical scrolling remain with the embedded page.
class _EdgeDrag extends HorizontalDragGestureRecognizer {
  bool enabled = false;

  @override
  bool isPointerAllowed(PointerEvent event) =>
      enabled && event.position.dx <= 24 && super.isPointerAllowed(event);
}

class EdgeBackGesture extends StatefulWidget {
  const EdgeBackGesture({
    super.key,
    required this.enabled,
    required this.onBack,
    required this.child,
  });

  final bool enabled;
  final VoidCallback onBack;
  final Widget child;

  @override
  State<EdgeBackGesture> createState() => _EdgeBackGestureState();
}

class _EdgeBackGestureState extends State<EdgeBackGesture> {
  double distance = 0;

  @override
  Widget build(BuildContext context) => RawGestureDetector(
    excludeFromSemantics: true,
    behavior: HitTestBehavior.translucent,
    gestures: {
      _EdgeDrag: GestureRecognizerFactoryWithHandlers<_EdgeDrag>(
        _EdgeDrag.new,
        (gesture) => gesture
          ..enabled = widget.enabled
          ..onStart = (_) {
            distance = 0;
          }
          ..onUpdate = (event) {
            distance += event.primaryDelta ?? 0;
          }
          ..onCancel = () {
            distance = 0;
          }
          ..onEnd = (event) {
            final complete =
                distance >= 72 ||
                (distance >= 24 && (event.primaryVelocity ?? 0) >= 600);
            distance = 0;
            if (complete && widget.enabled) widget.onBack();
          },
      ),
    },
    child: widget.child,
  );
}
