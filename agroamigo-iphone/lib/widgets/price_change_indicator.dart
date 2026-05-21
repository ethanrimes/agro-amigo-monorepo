import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';
import 'package:agroamigo_iphone/services/format.dart';

/// Port of `PriceChangeIndicator.tsx`.
/// Renders a colored badge with an arrow icon and formatted percentage.
/// Returns [SizedBox.shrink] when [value] is null.
class PriceChangeIndicator extends StatelessWidget {
  const PriceChangeIndicator({
    super.key,
    required this.value,
    this.size = IndicatorSize.md,
  });

  final double? value;
  final IndicatorSize size;

  @override
  Widget build(BuildContext context) {
    if (value == null) return const SizedBox.shrink();

    final v = value!;
    final isNeutral = v.abs() < 0.1;
    final isUp = v > 0;

    final color = isNeutral
        ? AppColors.priceNeutral
        : isUp
            ? AppColors.priceUp
            : AppColors.priceDown;

    final icon = isNeutral
        ? CupertinoIcons.minus
        : isUp
            ? CupertinoIcons.arrow_up
            : CupertinoIcons.arrow_down;

    final double iconSize;
    final double textSize;
    switch (size) {
      case IndicatorSize.sm:
        iconSize = 10;
        textSize = AppFontSize.xs;
        break;
      case IndicatorSize.lg:
        iconSize = 18;
        textSize = AppFontSize.lg;
        break;
      case IndicatorSize.md:
      default:
        iconSize = 14;
        textSize = AppFontSize.sm;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.094),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: iconSize, color: color),
          const SizedBox(width: 2),
          Text(
            formatPctChange(v),
            style: TextStyle(
                fontSize: textSize,
                fontWeight: FontWeight.w600,
                color: color),
          ),
        ],
      ),
    );
  }
}

enum IndicatorSize { sm, md, lg }
