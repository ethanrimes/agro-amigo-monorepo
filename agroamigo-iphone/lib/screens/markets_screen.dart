import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/markets_api.dart';
import '../services/cache.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../widgets/card.dart';
import '../widgets/search_bar.dart';
import 'market_detail_screen.dart';

/// Port of `agroamigo-app/app/(tabs)/markets.tsx`.
///
/// Markets are grouped by department; the search filters by market name,
/// city or department name (case-insensitive, min 2 chars to match the RN).
class MarketsScreen extends StatefulWidget {
  const MarketsScreen({super.key});

  @override
  State<MarketsScreen> createState() => _MarketsScreenState();
}

class _MarketSection {
  final String title;
  final List<_MarketItem> items;
  _MarketSection(this.title, this.items);
}

class _MarketItem {
  final String id;
  final String canonicalName;
  final String cityName;
  final String departmentName;
  _MarketItem({
    required this.id,
    required this.canonicalName,
    required this.cityName,
    required this.departmentName,
  });
}

class _MarketsScreenState extends State<MarketsScreen> {
  List<_MarketSection> _sections = [];
  String _search = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await AppCache.instance
          .cachedCall<List<Map<String, dynamic>>>('markets:all', getMarkets);

      final grouped = <String, List<_MarketItem>>{};
      for (final m in data) {
        final city = m['dim_city'] as Map<String, dynamic>?;
        final dept = (city?['dim_department'] as Map<String, dynamic>?)
                ?['canonical_name'] as String? ??
            'Otro';
        final cityName = city?['canonical_name'] as String? ?? '';
        final item = _MarketItem(
          id: m['id'] as String,
          canonicalName: (m['canonical_name'] as String?) ?? '',
          cityName: cityName,
          departmentName: dept,
        );
        grouped.putIfAbsent(dept, () => []).add(item);
      }

      final secs = grouped.entries
          .map((e) => _MarketSection(e.key, e.value))
          .toList()
        ..sort((a, b) => a.title.compareTo(b.title));

      if (!mounted) return;
      setState(() {
        _sections = secs;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  List<_MarketSection> get _filtered {
    if (_search.length < 2) return _sections;
    final q = _search.toLowerCase();
    final out = <_MarketSection>[];
    for (final s in _sections) {
      final filtered = s.items.where((m) {
        return m.canonicalName.toLowerCase().contains(q) ||
            m.cityName.toLowerCase().contains(q) ||
            m.departmentName.toLowerCase().contains(q);
      }).toList();
      if (filtered.isNotEmpty) {
        out.add(_MarketSection(s.title, filtered));
      }
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.watch<SettingsProvider>().t;
    final scale = context.watch<SettingsProvider>().settings.fontSizeScale;

    if (_loading) {
      return const Center(child: CupertinoActivityIndicator(radius: 14));
    }

    final sections = _filtered;
    final isEmpty = sections.isEmpty;

    return CupertinoScrollbar(
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(
            parent: BouncingScrollPhysics()),
        slivers: [
          CupertinoSliverRefreshControl(
            onRefresh: () async {
              AppCache.instance.delete('markets:all');
              await _load();
            },
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.sm),
              child: AppSearchBar(
                value: _search,
                onChanged: (v) => setState(() => _search = v),
                placeholder: t.markets_search,
              ),
            ),
          ),
          if (isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: const EdgeInsets.only(top: 40),
                child: Text(
                  t.markets_not_found,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppFontSize.md * scale,
                    color: AppColors.textTertiary,
                  ),
                ),
              ),
            )
          else
            for (final section in sections) ..._buildSection(section, scale),
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
    );
  }

  List<Widget> _buildSection(_MarketSection section, double scale) {
    return [
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.only(
              left: AppSpacing.lg,
              right: AppSpacing.lg,
              top: AppSpacing.lg,
              bottom: AppSpacing.sm),
          child: Row(
            children: [
              const Icon(CupertinoIcons.location_solid,
                  size: 14, color: AppColors.primary),
              const SizedBox(width: AppSpacing.sm),
              Text(
                section.title,
                style: TextStyle(
                  fontSize: AppFontSize.md * scale,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
        ),
      ),
      SliverList(
        delegate: SliverChildBuilderDelegate(
          (context, i) {
            final m = section.items[i];
            return Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
              child: AppCard(
                onTap: () => Navigator.of(context).push(
                  CupertinoPageRoute(
                    builder: (_) => MarketDetailScreen(marketId: m.id),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                      child: const Icon(CupertinoIcons.cart,
                          size: 24, color: AppColors.primary),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            m.canonicalName,
                            style: TextStyle(
                              fontSize: AppFontSize.md * scale,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textPrimary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            m.cityName,
                            style: TextStyle(
                              fontSize: AppFontSize.sm * scale,
                              color: AppColors.textSecondary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    const Icon(CupertinoIcons.chevron_forward,
                        size: 18, color: AppColors.textTertiary),
                  ],
                ),
              ),
            );
          },
          childCount: section.items.length,
        ),
      ),
    ];
  }
}
