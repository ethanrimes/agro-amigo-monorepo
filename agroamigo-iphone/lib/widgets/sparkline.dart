import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';

/// Port of `Sparkline.tsx`.
/// Renders a miniature polyline using [CustomPainter].
/// Color is determined by trend: last >= first → [AppColors.priceUp] (orange),
/// otherwise [AppColors.priceDown] (blue).
class Sparkline extends StatelessWidget {
  const Sparkline({
    super.key,
    required this.data,
    this.width = 60,
    this.height = 24,
    this.color,
  });

  final List<double> data;
  final double width;
  final double height;
  /// Override trend color. When null the trend direction sets the color.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    if (data.length < 2) {
      return SizedBox(width: width, height: height);
    }

    final trendColor = color ??
        (data.last >= data.first ? AppColors.priceUp : AppColors.priceDown);

    return CustomPaint(
      size: Size(width, height),
      painter: _SparklinePainter(data: data, color: trendColor),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  const _SparklinePainter({required this.data, required this.color});

  final List<double> data;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    const padding = 2.0;
    final min = data.reduce((a, b) => a < b ? a : b);
    final max = data.reduce((a, b) => a > b ? a : b);
    final range = (max - min) == 0 ? 1.0 : (max - min);

    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;

    final path = Path();
    for (int i = 0; i < data.length; i++) {
      final x = padding +
          (i / (data.length - 1)) * (size.width - padding * 2);
      final y = padding +
          (1 - (data[i] - min) / range) * (size.height - padding * 2);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_SparklinePainter old) =>
      old.data != data || old.color != color;
}
