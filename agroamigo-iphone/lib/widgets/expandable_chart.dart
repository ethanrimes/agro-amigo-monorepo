import 'package:flutter/cupertino.dart';
import 'package:agroamigo_iphone/theme/theme.dart';

/// Port of `ExpandableChart.tsx`.
///
/// Generic widget that:
/// 1. Shows a collapsible header (title, subtitle, icon, badge, chevron).
/// 2. Lazily fetches data via [fetcher] the first time the section is expanded.
/// 3. Delegates rendering to [render] once data arrives.
/// 4. Provides default loading / error views, both overridable.
/// 5. Fires [onData] whenever the fetched value changes.
class ExpandableChart<T> extends StatefulWidget {
  const ExpandableChart({
    super.key,
    required this.title,
    required this.fetcher,
    required this.render,
    this.subtitle,
    this.icon,
    this.badge,
    this.initiallyExpanded = false,
    this.loadingView,
    this.errorBuilder,
    this.onData,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final dynamic badge; // String | int
  final Future<T> Function() fetcher;
  final Widget Function(T data) render;
  final bool initiallyExpanded;
  final Widget? loadingView;
  final Widget Function(Object error)? errorBuilder;
  final ValueChanged<T>? onData;

  @override
  State<ExpandableChart<T>> createState() => _ExpandableChartState<T>();
}

class _ExpandableChartState<T> extends State<ExpandableChart<T>> {
  late bool _expanded;
  Future<T>? _future;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
    if (_expanded) _fetchIfNeeded();
  }

  void _fetchIfNeeded() {
    _future ??= widget.fetcher()
      ..then((data) {
        if (mounted) widget.onData?.call(data);
      });
  }

  void _toggle() {
    setState(() {
      _expanded = !_expanded;
      if (_expanded) _fetchIfNeeded();
    });
  }

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header
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
                        Text(widget.title,
                            style: const TextStyle(
                                fontSize: AppFontSize.md,
                                fontWeight: FontWeight.w700,
                                color: AppColors.textPrimary)),
                        if (widget.subtitle != null)
                          Text(widget.subtitle!,
                              style: const TextStyle(
                                  fontSize: AppFontSize.xs,
                                  color: AppColors.textTertiary)),
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
                      child: Text('${widget.badge}',
                          style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              fontWeight: FontWeight.w600,
                              color: AppColors.primary)),
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

          // Content
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: _expanded
                ? Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: FutureBuilder<T>(
                      future: _future,
                      builder: (context, snap) {
                        if (snap.connectionState ==
                                ConnectionState.waiting &&
                            !snap.hasData) {
                          return widget.loadingView ??
                              const Padding(
                                padding: EdgeInsets.symmetric(
                                    vertical: AppSpacing.md),
                                child: CupertinoActivityIndicator(),
                              );
                        }
                        if (snap.hasError && !snap.hasData) {
                          if (widget.errorBuilder != null) {
                            return widget.errorBuilder!(snap.error!);
                          }
                          return Padding(
                            padding: const EdgeInsets.symmetric(
                                vertical: AppSpacing.sm),
                            child: Text(
                              'Error: ${snap.error}',
                              style: const TextStyle(
                                  fontSize: AppFontSize.sm,
                                  color: Color(0xFFc0392b)),
                            ),
                          );
                        }
                        if (snap.hasData) {
                          return widget.render(snap.data as T);
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  )
                : const SizedBox(width: double.infinity, height: 0),
          ),
        ],
      ),
    );
  }
}
