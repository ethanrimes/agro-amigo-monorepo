import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/markets_api.dart';
import '../services/cache.dart';
import '../services/format.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../widgets/app_card.dart';
import '../widgets/comments_section.dart';
import '../widgets/expandable_section.dart';
import '../widgets/market_supply_comparator.dart';
import 'product_detail_screen.dart';

/// Port of `agroamigo-app/app/market/[id].tsx`.
///
/// Loads the market entity + most-recent products eagerly. Supply summary
/// (server-aggregated via RPCs) and the supply comparator are gated behind
/// expandable sections so the page shell renders fast.
class MarketDetailScreen extends StatefulWidget {
  final String marketId;
  const MarketDetailScreen({super.key, required this.marketId});

  @override
  State<MarketDetailScreen> createState() => _MarketDetailScreenState();
}

const _supplyColors = <Color>[
  AppColors.primary,
  AppColors.accentOrange,
  AppColors.accentBlue,
  AppColors.secondary,
  AppColors.primaryLight,
  Color(0xFF9C27B0),
  Color(0xFF00BCD4),
  Color(0xFFFF5722),
];

class _MarketDetailScreenState extends State<MarketDetailScreen> {
  Map<String, dynamic>? _market;
  List<Map<String, dynamic>> _products = [];
  List<Map<String, dynamic>> _supply = [];
  List<Map<String, dynamic>> _allMarkets = [];
  bool _loading = true;

  // Supply section state.
  int _supplyTimeRange = 1; // default 1m
  String? _selectedSupplyProduct;
  String? _selectedSupplyProv;
  Map<String, dynamic>? _supplySummary;
  List<Map<String, dynamic>> _topSuppliedProducts = [];
  List<Map<String, dynamic>> _provenanceBars = [];
  bool _supplyLoading = false;

  // Lazy-load gates.
  bool _supplyExpanded = false;
  bool _supplyComparatorExpanded = false;

  String get _id => widget.marketId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        AppCache.instance.cachedCall<Map<String, dynamic>?>(
          'market:$_id:entity',
          () => getMarketById(_id),
        ),
        AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
          'market:$_id:products:200',
          () => getMarketProducts(_id, limit: 200),
        ),
      ]);

      final mkt = results[0] as Map<String, dynamic>?;
      final prods = (results[1] as List<Map<String, dynamic>>);

      // Dedupe — keep most recent observation per product.
      final byProduct = <String, Map<String, dynamic>>{};
      for (final p in prods) {
        final pid = p['product_id'] as String?;
        if (pid == null) continue;
        final pd = p['price_date'] as String? ?? '';
        final existing = byProduct[pid];
        if (existing == null ||
            pd.compareTo(existing['price_date'] as String? ?? '') > 0) {
          byProduct[pid] = p;
        }
      }

      if (!mounted) return;
      setState(() {
        _market = mkt;
        _products = byProduct.values.toList();
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    AppCache.instance.invalidatePrefix('market:$_id');
    await _load();
    if (_supplyExpanded) await _loadSupply();
    if (_supplyComparatorExpanded) await _loadComparatorData();
  }

  Future<void> _loadComparatorData() async {
    try {
      final m = await AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
        'markets:all',
        getMarkets,
      );
      final s = await AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
        'market:$_id:supply:30',
        () => getMarketSupply(_id, 30),
      );
      if (!mounted) return;
      setState(() {
        _allMarkets = m;
        _supply = s;
      });
    } catch (_) {/* swallow */}
  }

  List<_TimeRange> _supplyRanges(SettingsProvider sp) => [
        _TimeRange(sp.t.time_1w, 7),
        _TimeRange(sp.t.time_1m, 30),
        _TimeRange(sp.t.time_3m, 90),
        _TimeRange(sp.t.time_6m, 180),
        _TimeRange(sp.t.time_1y, 365),
        _TimeRange(sp.t.time_all, 0),
      ];

  Future<void> _loadSupply() async {
    if (!mounted) return;
    final ranges = _supplyRanges(context.read<SettingsProvider>());
    final tr = ranges[_supplyTimeRange];
    final days = tr.days;
    final keyBase =
        'market:$_id:supply:$days:${_selectedSupplyProduct ?? ''}:${_selectedSupplyProv ?? ''}';
    setState(() => _supplyLoading = true);
    try {
      final results = await Future.wait([
        AppCache.instance
            .cachedCall<Map<String, dynamic>?>(
              '$keyBase:summary',
              () => getMarketSupplySummary(
                _id,
                days,
                _selectedSupplyProduct,
                _selectedSupplyProv,
              ),
            )
            .catchError((_) => null),
        AppCache.instance
            .cachedCall<List<Map<String, dynamic>>>(
              '$keyBase:topProducts',
              () => getMarketTopProducts(
                  _id, days, _selectedSupplyProv, 10),
            )
            .catchError((_) => <Map<String, dynamic>>[]),
        AppCache.instance
            .cachedCall<List<Map<String, dynamic>>>(
              '$keyBase:topProv',
              () => getMarketTopProvenance(
                  _id, days, _selectedSupplyProduct, 15),
            )
            .catchError((_) => <Map<String, dynamic>>[]),
      ]);
      if (!mounted) return;
      setState(() {
        _supplySummary = results[0] as Map<String, dynamic>?;
        _topSuppliedProducts = results[1] as List<Map<String, dynamic>>;
        _provenanceBars = results[2] as List<Map<String, dynamic>>;
        _supplyLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _supplyLoading = false);
    }
  }

  // ── Derived state ─────────────────────────────────────────────────────
  List<_CategoryGroup> get _categoryGroups {
    final catMap = <String, Map<String, List<Map<String, dynamic>>>>{};
    for (final p in _products) {
      final dimProduct = p['dim_product'] as Map<String, dynamic>?;
      final sub = dimProduct?['dim_subcategory'] as Map<String, dynamic>?;
      final catName = (sub?['dim_category'] as Map<String, dynamic>?)
              ?['canonical_name'] as String? ??
          'Otro';
      final subName = sub?['canonical_name'] as String? ?? 'General';
      catMap.putIfAbsent(catName, () => {});
      catMap[catName]!.putIfAbsent(subName, () => []).add(p);
    }
    final out = catMap.entries.map((e) {
      final subs = e.value.entries
          .map((se) => _SubcategoryGroup(se.key, se.value))
          .toList()
        ..sort((a, b) => a.name.compareTo(b.name));
      return _CategoryGroup(e.key, subs);
    }).toList()
      ..sort((a, b) => a.category.compareTo(b.category));
    return out;
  }

  String? get _sharedDate {
    if (_products.isEmpty) return null;
    final first = _products.first['price_date'] as String?;
    if (first == null) return null;
    final allSame =
        _products.every((p) => (p['price_date'] as String?) == first);
    return allSame ? first : null;
  }

  @override
  Widget build(BuildContext context) {
    final sp = context.watch<SettingsProvider>();
    final t = sp.t;
    final scale = sp.settings.fontSizeScale;

    if (_loading) {
      return const CupertinoPageScaffold(
        navigationBar: CupertinoNavigationBar(
          backgroundColor: AppColors.dark,
          middle: Text('', style: TextStyle(color: AppColors.textInverse)),
        ),
        child: Center(child: CupertinoActivityIndicator(radius: 14)),
      );
    }

    if (_market == null) {
      return CupertinoPageScaffold(
        navigationBar: const CupertinoNavigationBar(
          backgroundColor: AppColors.dark,
          middle: Text('', style: TextStyle(color: AppColors.textInverse)),
        ),
        child: Center(
          child: Text(t.market_not_found,
              style: TextStyle(
                  fontSize: AppFontSize.md * scale,
                  color: AppColors.textPrimary)),
        ),
      );
    }

    final mkt = _market!;
    final city = mkt['dim_city'] as Map<String, dynamic>?;
    final cityName = city?['canonical_name'] as String? ?? '';
    final deptName = (city?['dim_department'] as Map<String, dynamic>?)
            ?['canonical_name'] as String? ??
        '';
    final marketName = mkt['canonical_name'] as String? ?? '';

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text(
          marketName,
          style: const TextStyle(color: AppColors.textInverse),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        previousPageTitle: '',
      ),
      child: CupertinoScrollbar(
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(
              parent: BouncingScrollPhysics()),
          slivers: [
            CupertinoSliverRefreshControl(onRefresh: _refresh),

            // Header
            SliverToBoxAdapter(
              child: _buildHeader(marketName, cityName, deptName, scale),
            ),

            // Stats row
            SliverToBoxAdapter(
              child: _buildStatsRow(t, scale),
            ),

            // Prices section header
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(
                    left: AppSpacing.lg,
                    right: AppSpacing.lg,
                    top: AppSpacing.lg,
                    bottom: AppSpacing.xs),
                child: Row(
                  children: [
                    const Icon(CupertinoIcons.tag,
                        size: 18, color: AppColors.primary),
                    const SizedBox(width: AppSpacing.sm),
                    Text(
                      t.product_price_section,
                      style: TextStyle(
                        fontSize: AppFontSize.lg * scale,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Products grouped by category
            SliverToBoxAdapter(
              child: _buildProductsCard(t, scale),
            ),

            // Supply section
            SliverToBoxAdapter(
              child: _buildSupplyCard(t, scale, sp),
            ),

            // Supply comparator
            SliverToBoxAdapter(
              child: _buildSupplyComparator(t, scale),
            ),

            // Comments
            if (sp.settings.commentsEnabled)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                      AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
                  child: AppCard(
                    child: CommentsSection(
                      entityType: 'market',
                      entityId: _id,
                    ),
                  ),
                ),
              ),

            const SliverToBoxAdapter(child: SizedBox(height: 40)),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(
      String name, String city, String dept, double scale) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(
          bottom: BorderSide(color: AppColors.borderLight, width: 1),
        ),
      ),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(AppRadius.lg),
            ),
            child: const Icon(CupertinoIcons.cart,
                size: 36, color: AppColors.primary),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    fontSize: AppFontSize.xl * scale,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(CupertinoIcons.location_solid,
                        size: 14, color: AppColors.textTertiary),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        '$city${dept.isNotEmpty ? ', $dept' : ''}',
                        style: TextStyle(
                          fontSize: AppFontSize.sm * scale,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatsRow(t, double scale) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Row(
        children: [
          Expanded(
            child: _StatBox(
                value: '${_products.length}',
                label: t.market_products,
                scale: scale),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _StatBox(
                value: '${_categoryGroups.length}',
                label: t.market_categories,
                scale: scale),
          ),
        ],
      ),
    );
  }

  Widget _buildProductsCard(t, double scale) {
    final shared = _sharedDate;
    final groups = _categoryGroups;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              t.market_recent_products,
              style: TextStyle(
                fontSize: AppFontSize.md * scale,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            if (shared != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${t.market_prices_at} ${formatDateShort(shared)}',
                  style: TextStyle(
                    fontSize: AppFontSize.xs * scale,
                    color: AppColors.textTertiary,
                  ),
                ),
              ),
            const SizedBox(height: AppSpacing.sm),
            if (_products.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
                child: Text(
                  t.market_no_recent_data,
                  style: TextStyle(
                    fontSize: AppFontSize.sm * scale,
                    color: AppColors.textTertiary,
                  ),
                ),
              )
            else
              for (int gi = 0; gi < groups.length; gi++)
                ExpandableSection(
                  title: groups[gi].category,
                  icon: CupertinoIcons.leaf_arrow_circlepath,
                  badge: groups[gi]
                      .subcategories
                      .fold<int>(0, (s, sub) => s + sub.items.length),
                  initiallyExpanded: gi < 3,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final sub in groups[gi].subcategories)
                        _buildSubcategory(
                            sub, groups[gi].subcategories.length > 1, t,
                            scale, shared),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }

  Widget _buildSubcategory(_SubcategoryGroup sub, bool showHeader, t,
      double scale, String? shared) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (showHeader)
          Padding(
            padding: const EdgeInsets.only(
                top: AppSpacing.sm, bottom: AppSpacing.xs),
            child: Text(
              sub.name,
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                fontWeight: FontWeight.w600,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        for (final p in sub.items)
          _buildProductRow(p, t, scale, shared),
      ],
    );
  }

  Widget _buildProductRow(
      Map<String, dynamic> p, t, double scale, String? shared) {
    final dimProduct = p['dim_product'] as Map<String, dynamic>?;
    final productName =
        dimProduct?['canonical_name'] as String? ?? t.market_product_fallback;
    final presentation = (p['dim_presentation'] as Map<String, dynamic>?)
        ?['canonical_name'] as String?;
    final units = (p['dim_units'] as Map<String, dynamic>?)
        ?['canonical_name'] as String?;
    final ctx = formatPriceContext(presentation, units);
    final minP = p['min_price'] as num?;
    final maxP = p['max_price'] as num?;
    final priceText = (minP == null)
        ? '—'
        : (maxP != null && maxP != minP)
            ? '${formatCOP(minP)} - ${formatCOP(maxP)}'
            : formatCOP(minP);
    final priceDate = p['price_date'] as String?;
    final pid = p['product_id'] as String?;

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.sm),
        onTap: pid == null
            ? null
            : () => Navigator.of(context).push(
                  CupertinoPageRoute(
                    builder: (_) => ProductDetailScreen(productId: pid),
                  ),
                ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    productName,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (ctx.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        ctx,
                        style: TextStyle(
                          fontSize: AppFontSize.xs * scale,
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  priceText,
                  style: TextStyle(
                    fontSize: AppFontSize.md * scale,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                if (shared == null && priceDate != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      formatDateShort(priceDate),
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSupplyCard(t, double scale, SettingsProvider sp) {
    final ranges = _supplyRanges(sp);
    final summary = _supplySummary;
    final totalKg = (summary?['total_kg'] as num?) ?? 0;
    final dailyAvg = (summary?['daily_avg_kg'] as num?) ?? 0;
    final oldest = summary?['oldest_obs'] as String?;
    final newest = summary?['newest_obs'] as String?;
    final numDays = (summary?['num_days'] as num?) ?? 0;

    return Padding(
      padding: const EdgeInsets.only(
          left: AppSpacing.lg,
          right: AppSpacing.lg,
          top: AppSpacing.sm),
      child: AppCard(
        child: ExpandableSection(
          title: t.product_supply_section,
          icon: CupertinoIcons.cube_box,
          initiallyExpanded: false,
          onExpandChange: (open) {
            setState(() => _supplyExpanded = open);
            if (open) _loadSupply();
          },
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (!_supplyLoading &&
                  _supplyExpanded &&
                  summary == null &&
                  _topSuppliedProducts.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
                  child: Text(
                    t.product_no_supply_data,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      color: AppColors.textTertiary,
                    ),
                  ),
                )
              else ...[
                // Time range tiles
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: [
                    for (int i = 0; i < ranges.length; i++)
                      _Tile(
                        label: ranges[i].label,
                        active: i == _supplyTimeRange,
                        onTap: () {
                          setState(() => _supplyTimeRange = i);
                          _loadSupply();
                        },
                        scale: scale,
                      ),
                  ],
                ),
                if (_selectedSupplyProduct != null ||
                    _selectedSupplyProv != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Wrap(
                    spacing: AppSpacing.xs,
                    runSpacing: AppSpacing.xs,
                    children: [
                      if (_selectedSupplyProduct != null)
                        _FilterPill(
                          icon: CupertinoIcons.cube_box,
                          label: _topSuppliedProducts.firstWhere(
                                (p) => p['product_id'] ==
                                    _selectedSupplyProduct,
                                orElse: () => <String, dynamic>{},
                              )['product_name'] as String? ??
                              t.market_product_fallback,
                          color: AppColors.accentBlue,
                          onClear: () {
                            setState(() => _selectedSupplyProduct = null);
                            _loadSupply();
                          },
                          scale: scale,
                        ),
                      if (_selectedSupplyProv != null)
                        _FilterPill(
                          icon: CupertinoIcons.location,
                          label: _selectedSupplyProv!,
                          color: AppColors.secondary,
                          onClear: () {
                            setState(() => _selectedSupplyProv = null);
                            _loadSupply();
                          },
                          scale: scale,
                        ),
                    ],
                  ),
                ],
                if (oldest != null && newest != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    '${formatDateShort(oldest)} – ${formatDateShort(newest)}'
                    '${numDays > 0 ? ' · ${numDays.toInt()} d' : ''}',
                    style: TextStyle(
                      fontSize: AppFontSize.xs * scale,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                // Stats row
                Row(
                  children: [
                    Expanded(
                      child: _StatBox(
                          value: formatKg(totalKg),
                          label: t.product_total,
                          scale: scale),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: _StatBox(
                          value: formatKg(dailyAvg),
                          label: t.product_daily_avg,
                          scale: scale),
                    ),
                  ],
                ),
                if (_supplyLoading) ...[
                  const SizedBox(height: AppSpacing.md),
                  const Center(child: CupertinoActivityIndicator()),
                ],
                // Top products
                if (_topSuppliedProducts.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    t.market_products,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(top: 2, bottom: AppSpacing.sm),
                    child: Text(
                      'Toca para ver procedencia.',
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
                  for (final d in _topSuppliedProducts)
                    _buildSupplyBar(
                      name: d['product_name'] as String? ?? '',
                      value: (d['total_kg'] as num?) ?? 0,
                      maxValue:
                          (_topSuppliedProducts.first['total_kg'] as num?) ?? 1,
                      active: _selectedSupplyProduct == d['product_id'],
                      dim: _selectedSupplyProduct != null &&
                          _selectedSupplyProduct != d['product_id'],
                      activeColor: AppColors.accentBlue,
                      barColor: AppColors.accentBlue,
                      onTap: () {
                        final pid = d['product_id'] as String?;
                        setState(() {
                          _selectedSupplyProduct =
                              _selectedSupplyProduct == pid ? null : pid;
                        });
                        _loadSupply();
                      },
                      scale: scale,
                    ),
                ],
                // Provenance
                if (_provenanceBars.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    t.product_provenance,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(top: 2, bottom: AppSpacing.sm),
                    child: Text(
                      'Toca para ver solo este origen.',
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
                  for (int i = 0; i < _provenanceBars.length; i++)
                    _buildSupplyBar(
                      name: _provenanceBars[i]['dept_name'] as String? ?? '',
                      value:
                          (_provenanceBars[i]['total_kg'] as num?) ?? 0,
                      maxValue:
                          (_provenanceBars.first['total_kg'] as num?) ?? 1,
                      active: _selectedSupplyProv ==
                          _provenanceBars[i]['dept_name'],
                      dim: _selectedSupplyProv != null &&
                          _selectedSupplyProv !=
                              _provenanceBars[i]['dept_name'],
                      activeColor: AppColors.secondary,
                      barColor:
                          _supplyColors[i % _supplyColors.length],
                      onTap: () {
                        final dept =
                            _provenanceBars[i]['dept_name'] as String?;
                        setState(() {
                          _selectedSupplyProv =
                              _selectedSupplyProv == dept ? null : dept;
                        });
                        _loadSupply();
                      },
                      scale: scale,
                    ),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSupplyBar({
    required String name,
    required num value,
    required num maxValue,
    required bool active,
    required bool dim,
    required Color activeColor,
    required Color barColor,
    required VoidCallback onTap,
    required double scale,
  }) {
    final pct = (maxValue == 0) ? 0.0 : (value / maxValue).clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Opacity(
          opacity: dim ? 0.4 : 1,
          child: Row(
            children: [
              SizedBox(
                width: 110,
                child: Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppFontSize.sm * scale,
                    fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                    color: active ? activeColor : AppColors.textPrimary,
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: AppColors.borderLight,
                    borderRadius: BorderRadius.circular(AppRadius.full),
                  ),
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: pct.toDouble(),
                    child: Container(
                      decoration: BoxDecoration(
                        color: barColor,
                        borderRadius: BorderRadius.circular(AppRadius.full),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              SizedBox(
                width: 64,
                child: Text(
                  formatKg(value),
                  textAlign: TextAlign.right,
                  style: TextStyle(
                    fontSize: AppFontSize.xs * scale,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSupplyComparator(t, double scale) {
    return Padding(
      padding: const EdgeInsets.only(
          left: AppSpacing.lg,
          right: AppSpacing.lg,
          top: AppSpacing.sm),
      child: AppCard(
        child: ExpandableSection(
          title: '${t.product_supply_section} · Comparar',
          icon: CupertinoIcons.chart_bar,
          initiallyExpanded: false,
          onExpandChange: (open) {
            setState(() => _supplyComparatorExpanded = open);
            if (open) _loadComparatorData();
          },
          child: MarketSupplyComparator(
            currentMarket: _market!,
            supply: _supply,
            products: _products,
            markets: _allMarkets,
          ),
        ),
      ),
    );
  }
}

class _TimeRange {
  final String label;
  final int days;
  _TimeRange(this.label, this.days);
}

class _CategoryGroup {
  final String category;
  final List<_SubcategoryGroup> subcategories;
  _CategoryGroup(this.category, this.subcategories);
}

class _SubcategoryGroup {
  final String name;
  final List<Map<String, dynamic>> items;
  _SubcategoryGroup(this.name, this.items);
}

class _StatBox extends StatelessWidget {
  final String value;
  final String label;
  final double scale;
  const _StatBox(
      {required this.value, required this.label, required this.scale});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: AppFontSize.xl * scale,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              fontSize: AppFontSize.xs * scale,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ),
    );
  }
}

class _Tile extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;
  final double scale;
  const _Tile(
      {required this.label,
      required this.active,
      required this.onTap,
      required this.scale});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: active ? AppColors.accentBlue : AppColors.surface,
          border: Border.all(
              color: active ? AppColors.accentBlue : AppColors.border),
          borderRadius: BorderRadius.circular(AppRadius.full),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppFontSize.sm * scale,
            fontWeight: FontWeight.w600,
            color: active ? AppColors.textInverse : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}

class _FilterPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onClear;
  final double scale;
  const _FilterPill({
    required this.icon,
    required this.label,
    required this.color,
    required this.onClear,
    required this.scale,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onClear,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppRadius.full),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 12, color: color),
            const SizedBox(width: AppSpacing.xs),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 160),
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppFontSize.xs * scale,
                  color: color,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Icon(CupertinoIcons.clear_circled_solid, size: 14, color: color),
          ],
        ),
      ),
    );
  }
}
