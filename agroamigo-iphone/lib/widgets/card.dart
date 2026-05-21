import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';

/// Port of `Card.tsx`.
/// Pressable variant: wraps in CupertinoButton with opacity/scale feedback.
class AppCard extends StatelessWidget {
  AppCard({
    super.key,
    required this.child,
    VoidCallback? onPressed,
    VoidCallback? onTap,
    this.padding = AppSpacing.lg,
    this.style,
  }) : onPressed = onPressed ?? onTap;

  final Widget child;
  final VoidCallback? onPressed;
  final double padding;
  final BoxDecoration? style;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      padding: EdgeInsets.all(padding),
      decoration: (style ?? const BoxDecoration()).copyWith(
        color: style?.color ?? AppColors.surface,
        borderRadius:
            style?.borderRadius ?? BorderRadius.circular(AppRadius.lg),
        boxShadow: style?.boxShadow ??
            [
              BoxShadow(
                color: AppColors.dark.withOpacity(0.06),
                offset: const Offset(0, 2),
                blurRadius: 8,
              ),
            ],
      ),
      child: child,
    );

    if (onPressed != null) {
      return CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: content,
      );
    }
    return content;
  }
}
