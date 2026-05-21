import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';

/// Port of `ExpandableSection.tsx`.
/// Uses AnimatedSize for smooth expand/collapse animation.
/// Fires [onExpandChange] on each toggle (parents can lazy-load section data).
class ExpandableSection extends StatefulWidget {
  const ExpandableSection({
    super.key,
    required this.title,
    required this.child,
    this.subtitle,
    this.initiallyExpanded = false,
    this.icon,
    this.badge,
    this.onExpandChange,
  });

  final String title;
  final String? subtitle;
  final bool initiallyExpanded;
  final Widget child;
  final IconData? icon;
  final dynamic badge; // String | int
  final ValueChanged<bool>? onExpandChange;

  @override
  State<ExpandableSection> createState() => _ExpandableSectionState();
}

class _ExpandableSectionState extends State<ExpandableSection>
    with SingleTickerProviderStateMixin {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
    if (_expanded) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        widget.onExpandChange?.call(true);
      });
    }
  }

  void _toggle() {
    setState(() => _expanded = !_expanded);
    widget.onExpandChange?.call(_expanded);
  }

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header row
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: _toggle,
            child: Padding(
              padding:
                  const EdgeInsets.symmetric(vertical: AppSpacing.sm),
              child: Row(
                children: [
                  if (widget.icon != null) ...[
                    Icon(widget.icon, size: 16, color: AppColors.textSecondary),
                    const SizedBox(width: AppSpacing.sm),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          widget.title,
                          style: const TextStyle(
                              fontSize: AppFontSize.md,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary),
                        ),
                        if (widget.subtitle != null)
                          Text(
                            widget.subtitle!,
                            style: const TextStyle(
                                fontSize: AppFontSize.xs,
                                color: AppColors.textTertiary),
                          ),
                      ],
                    ),
                  ),
                  if (widget.badge != null) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(AppRadius.full),
                      ),
                      child: Text(
                        '${widget.badge}',
                        style: const TextStyle(
                            fontSize: AppFontSize.xs,
                            fontWeight: FontWeight.w600,
                            color: AppColors.primary),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                  ],
                  Icon(
                    _expanded
                        ? CupertinoIcons.chevron_up
                        : CupertinoIcons.chevron_down,
                    size: 18,
                    color: AppColors.textTertiary,
                  ),
                ],
              ),
            ),
          ),

          // Content with AnimatedSize
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: _expanded
                ? Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: widget.child,
                  )
                : const SizedBox(width: double.infinity, height: 0),
          ),
        ],
      ),
    );
  }
}
