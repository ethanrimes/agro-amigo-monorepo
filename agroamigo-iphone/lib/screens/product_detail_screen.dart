import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/comments_api.dart';
import '../api/image_attribution_api.dart';
import '../api/products_api.dart';
import '../api/supply_api.dart';
import '../services/cache.dart';
import '../services/format.dart';
import '../state/settings_provider.dart';
import '../state/watchlist_provider.dart';
import '../theme/theme.dart';
import '../widgets/card.dart';
import '../widgets/comments_section.dart';
import '../widgets/expandable_section.dart';
import '../widgets/line_chart.dart';
import '../widgets/price_change_indicator.dart';
import '../widgets/product_image.dart';

/// Port of `agroamigo-app/app/product/[id].tsx`.
///
/// Renders product header, price + supply sections, prices-by-market table,
/// provenance, comments and image attribution. All heavy fetches are cached
/// through [AppCache] and lazy-loaded as the user expands sections.
class ProductDetailScreen extends StatefulWidget {
  final String productId;
  const ProductDetailScreen({super.key, required this.productId});

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _TimeRange {
  final String label;
  final int days;
  const _TimeRange(this.label, this.days);
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
  // ── data ───────────────────────────────────────────────────────────
  Map<String, dynamic>? _product;
  List<dynamic> _prices = const [];
  List<dynamic> _marketPrices = const [];

  Map<String, dynamic>? _supplySummary;
  List<Map<String, dynamic>> _supplyByDate = const [];
  List<Map<String, dynamic>> _topDestinations = const [];
  List<Map<String, dynamic>> _topOrigins = const [];

  Map<String, dynamic>? _imageAttribution;

  bool _loading = true;
  bool _priceChartExpanded = false;
  bool _supplyExpanded = false;

  // ── price-section filters ──────────────────────────────────────────
  int? _timeRangeIdx;
  String? _selectedMarketId;
  String? _selectedPresentation;
  bool _showWeekTooltip = false;

  // ── prices-by-market filters ───────────────────────────────────────
  String? _mktPresFilter;
  bool _mktSortAsc = false;

  // ── supply filters ─────────────────────────────────────────────────
  int _supplyTimeRangeIdx = 1; // default 1m
  String? _supplyProvFilter;
  String? _supplyMarketId;

  late List<_TimeRange> _timeRanges;

  static const List<Color> _supplyColors = [
    AppColors.primary,
    AppColors.accentOrange,
    AppColors.accentBlue,
    AppColors.secondary,
    AppColors.primaryLight,
    Color(0xFF9C27B0),
    Color(0xFF00BCD4),
    Color(0xFFFF5722),
  ];

  @override
  void initState() {
    super.initState();
    _loadProduct();
  }

  void _refreshTimeRanges(BuildContext context) {
    final t = context.read<SettingsProvider>().t;
    _timeRanges = [
      _TimeRange(t.time_1w, 7),
      _TimeRange(t.time_1m, 30),
      _TimeRange(t.time_3m, 90),
      _TimeRange(t.time_6m, 180),
      _TimeRange(t.time_1y, 365),
      _TimeRange(t.time_all, 0),
    ];
  }

  Future<void> _loadProduct() async {
    setState(() => _loading = true);
    try {
      final id = widget.productId;
      final results = await Future.wait([
        AppCache.instance.cachedCall<dynamic>(
          'product:$id:entity',
          () => getProductById(id),
        ),
        AppCache.instance.cachedCall<List<dynamic>>(
          'product:$id:prices-by-market',
          () async => (await getProductPricesByMarket(id, limit: 100)),
        ),
        AppCache.instance.cachedCall<dynamic>(
          'product:$id:image-attr',
          () async {
            final a = await getImageAttribution('product', id);
            if (a == null) return null;
            return <String, dynamic>{
              'author': a.author,
              'source_name': a.sourceName,
              'license': a.license,
            };
          },
        ),
      ]);
      if (!mounted) return;
      setState(() {
        _product = (results[0] as Map?)?.cast<String, dynamic>();
        _marketPrices = (results[1] as List?) ?? const <dynamic>[];
        _imageAttribution =
            (results[2] as Map?)?.cast<String, dynamic>();
      });
    } catch (e) {
      // ignore: avoid_print
      print('Error loading product: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    AppCache.instance.invalidatePrefix('product:${widget.productId}');
    await _loadProduct();
    if (_priceChartExpanded) await _loadPrices();
    if (_supplyExpanded) await _loadSupply();
  }

  Future<void> _loadPrices() async {
    final id = widget.productId;
    try {
      final data = await AppCache.instance.cachedCall<List<dynamic>>(
        'product:$id:prices:all',
        () async =>
            (await getProductPrices(id, days: 36500, limit: 5000)) ??
                const <dynamic>[],
      );
      if (!mounted) return;
      setState(() => _prices = data);
    } catch (e) {
      // ignore: avoid_print
      print('Error loading prices: $e');
    }
  }

  Future<void> _loadSupply() async {
    final id = widget.productId;
    final tr = _timeRanges[_supplyTimeRangeIdx];
    final days = tr.days == 0 ? 36500 : tr.days;
    final keyBase =
        'product:$id:supply:$days:${_supplyMarketId ?? ''}:${_supplyProvFilter ?? ''}';
    try {
      final results = await Future.wait([
        AppCache.instance
            .cachedCall<dynamic>(
              '$keyBase:summary',
              () => getProductSupplySummary(
                  id, days, marketId: _supplyMarketId, provDept: _supplyProvFilter),
            )
            .catchError((_) => null),
        AppCache.instance
            .cachedCall<List<dynamic>>(
              '$keyBase:byDate',
              () async =>
                  (await getProductSupplyByDate(
                          id, days, marketId: _supplyMarketId, provDept: _supplyProvFilter)),
            )
            .catchError((_) => const <dynamic>[]),
        AppCache.instance
            .cachedCall<List<dynamic>>(
              '$keyBase:dests',
              () async =>
                  (await getProductTopDestinations(id, days, provDept: _supplyProvFilter, limit: 15)),
            )
            .catchError((_) => const <dynamic>[]),
        AppCache.instance
            .cachedCall<List<dynamic>>(
              '$keyBase:origins',
              () async =>
                  (await getProductTopOrigins(id, days, marketId: _supplyMarketId, limit: 15)),
            )
            .catchError((_) => const <dynamic>[]),
      ]);
      if (!mounted) return;
      setState(() {
        _supplySummary = (results[0] as Map?)?.cast<String, dynamic>();
        _supplyByDate = ((results[1] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList();
        _topDestinations = ((results[2] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList();
        _topOrigins = ((results[3] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => m.cast<String, dynamic>())
            .toList();
      });
    } catch (e) {
      // ignore: avoid_print
      print('Error loading supply: $e');
    }
  }

  // ── helpers (mirrors of TS source) ─────────────────────────────────

  String _fmtMarket(dynamic m) {
    if (m is! Map) return '';
    final name = (m['canonical_name'] as String?) ?? '';
    final city = (m['dim_city'] is Map)
        ? ((m['dim_city'] as Map)['canonical_name'] as String?) ?? ''
        : '';
    if (city.isEmpty || name.toLowerCase().contains(city.toLowerCase())) {
      return name;
    }
    return '$name ($city)';
  }

  String _presKey(dynamic p) =>
      '${p['presentation_id'] ?? ''}|${p['units_id'] ?? ''}';

  String _presLabel(dynamic p) {
    final pres = (p['dim_presentation'] is Map)
        ? (p['dim_presentation'] as Map)['canonical_name'] as String?
        : null;
    final units = (p['dim_units'] is Map)
        ? (p['dim_units'] as Map)['canonical_name'] as String?
        : null;
    return [pres, units]
        .where((s) => s != null && s.isNotEmpty)
        .join(' \u00b7 ');
  }

  // ── price cascade ──────────────────────────────────────────────────

  List<int> get _availablePriceRangeIdxs {
    if (_prices.isEmpty) return const [];
    final newest = _prices.first['price_date'] as String?;
    if (newest == null) return const [];
    final newestDate = DateTime.parse('${newest}T00:00:00');
    final daysOld = DateTime.now().difference(newestDate).inDays;
    final out = <int>[];
    for (var i = 0; i < _timeRanges.length; i++) {
      final tr = _timeRanges[i];
      if (tr.days == 0 || daysOld <= tr.days) out.add(i);
    }
    return out;
  }

  List<dynamic> get _timeFilteredPrices {
    final tr = _timeRanges[_timeRangeIdx ?? 0];
    if (tr.days == 0) return _prices;
    final since =
        DateTime.now().subtract(Duration(days: tr.days)).toIso8601String().substring(0, 10);
    return _prices.where((p) => (p['price_date'] as String).compareTo(since) >= 0).toList();
  }

  List<Map<String, String>> get _availableMarkets {
    final map = <String, Map<String, String>>{};
    for (final p in _timeFilteredPrices) {
      final id = p['market_id'] as String?;
      final dm = p['dim_market'];
      if (id != null && dm is Map && dm['canonical_name'] != null) {
        map.putIfAbsent(id, () => {'id': id, 'name': _fmtMarket(dm)});
      }
    }
    final list = map.values.toList();
    list.sort((a, b) => (a['name']!).compareTo(b['name']!));
    return list;
  }

  List<dynamic> get _marketFilteredPrices {
    if (_selectedMarketId == null) return _timeFilteredPrices;
    return _timeFilteredPrices
        .where((p) => p['market_id'] == _selectedMarketId)
        .toList();
  }

  List<Map<String, String>> _availablePresentationsFor(List<dynamic> rows) {
    final map = <String, String>{};
    for (final p in rows) {
      final pres = (p['dim_presentation'] is Map)
          ? (p['dim_presentation'] as Map)['canonical_name']
          : null;
      if (pres != null && p['presentation_id'] != null) {
        final key = _presKey(p);
        map.putIfAbsent(key, () => _presLabel(p));
      }
    }
    return map.entries.map((e) => {'id': e.key, 'name': e.value}).toList();
  }

  List<dynamic> get _filteredPrices {
    final pres = _availablePresentationsFor(_marketFilteredPrices);
    final selected = _selectedPresentation ??
        (pres.isNotEmpty ? pres.first['id'] : null);
    if (selected == null) return _marketFilteredPrices;
    return _marketFilteredPrices.where((p) => _presKey(p) == selected).toList();
  }

  // ── prices-by-market table data ────────────────────────────────────

  List<dynamic> get _marketPriceRows {
    var rows = List<dynamic>.from(_marketPrices);
    if (_mktPresFilter != null) {
      final parts = _mktPresFilter!.split('|');
      final presId = parts[0];
      final unitsId = parts.length > 1 ? parts[1] : '';
      rows = rows.where((p) {
        return p['presentation_id'] == presId &&
            ((p['units_id'] as String?) ?? '') == unitsId;
      }).toList();
    }
    final map = <String, dynamic>{};
    for (final p in rows) {
      final key = (p['market_id'] as String?) ?? 'unknown';
      final ex = map[key];
      if (ex == null ||
          (p['price_date'] as String).compareTo(ex['price_date'] as String) > 0) {
        map[key] = p;
      }
    }
    final out = map.values.toList();
    out.sort((a, b) {
      final ap = (a['avg_price'] as num?) ?? (a['min_price'] as num?) ?? 0;
      final bp = (b['avg_price'] as num?) ?? (b['min_price'] as num?) ?? 0;
      return _mktSortAsc ? ap.compareTo(bp) : bp.compareTo(ap);
    });
    return out;
  }

  ({double median, double mean}) get _mktStats {
    final avgs = <double>[];
    for (final p in _marketPriceRows) {
      final avg = (p['avg_price'] as num?)?.toDouble() ??
          (((p['min_price'] as num?)?.toDouble() ?? 0) +
                  ((p['max_price'] as num?)?.toDouble() ?? 0)) /
              2;
      if (avg > 0) avgs.add(avg);
    }
    if (avgs.isEmpty) return (median: 0, mean: 0);
    final sorted = [...avgs]..sort();
    final mid = sorted.length ~/ 2;
    final median = sorted.length.isEven
        ? (sorted[mid - 1] + sorted[mid]) / 2
        : sorted[mid];
    final mean = avgs.reduce((a, b) => a + b) / avgs.length;
    return (median: median, mean: mean);
  }

  // ── header info ────────────────────────────────────────────────────

  ({
    Map? latestObs,
    String mostCommonPres,
    String geoSource,
    double? weekChange,
    double displayMin,
    double displayMax,
  }) _headerInfo(SettingsProvider sp) {
    final t = sp.t;
    if (_marketPrices.isEmpty) {
      return (
        latestObs: null,
        mostCommonPres: '',
        geoSource: t.product_national_avg,
        weekChange: null,
        displayMin: 0,
        displayMax: 0,
      );
    }
    // Find the most common presentation+units bucket
    final presCounts = <String, ({int count, String label})>{};
    for (final p in _marketPrices) {
      final key = _presKey(p);
      final ex = presCounts[key];
      presCounts[key] = ex == null
          ? (count: 1, label: _presLabel(p))
          : (count: ex.count + 1, label: ex.label);
    }
    var mostCommonKey = '';
    var mostCommonPres = '';
    var maxCount = 0;
    presCounts.forEach((k, v) {
      if (v.count > maxCount) {
        maxCount = v.count;
        mostCommonKey = k;
        mostCommonPres = v.label;
      }
    });
    final bucket =
        _marketPrices.where((p) => _presKey(p) == mostCommonKey).toList();
    final dm = sp.settings.defaultMarket;
    Map? latestObs;
    var geoSource = t.product_national_avg;
    double displayMin = 0, displayMax = 0;

    if (dm.level == MarketLevel.mercado && dm.id != null) {
      final matches =
          bucket.where((p) => p['market_id'] == dm.id).toList();
      if (matches.isNotEmpty) {
        latestObs = matches.reduce((a, b) =>
            (a['price_date'] as String).compareTo(b['price_date'] as String) > 0
                ? a
                : b);
        geoSource = _fmtMarket(latestObs!['dim_market']);
        displayMin = ((latestObs!['min_price'] as num?) ??
                (latestObs!['avg_price'] as num?) ??
                0)
            .toDouble();
        displayMax = ((latestObs!['max_price'] as num?) ??
                (latestObs!['avg_price'] as num?) ??
                0)
            .toDouble();
      }
    }
    if (latestObs == null && bucket.isNotEmpty) {
      final latestDate = bucket.fold<String>(
          '',
          (a, p) => (p['price_date'] as String).compareTo(a) > 0
              ? p['price_date'] as String
              : a);
      final sameDay = bucket.where((p) => p['price_date'] == latestDate).toList();
      final mins = <num>[];
      final maxs = <num>[];
      for (final p in sameDay) {
        final mn = (p['min_price'] as num?) ?? (p['avg_price'] as num?);
        final mx = (p['max_price'] as num?) ?? (p['avg_price'] as num?);
        if (mn is num && mn > 0) mins.add(mn);
        if (mx is num && mx > 0) maxs.add(mx);
      }
      if (mins.isNotEmpty) {
        displayMin = mins.reduce((a, b) => a + b) / mins.length;
      }
      if (maxs.isNotEmpty) {
        displayMax = maxs.reduce((a, b) => a + b) / maxs.length;
      }
      latestObs = {'price_date': latestDate, 'dim_market': null};
      geoSource = t.product_national_avg;
    }

    double? weekChange;
    if (latestObs != null) {
      final latestDate = DateTime.parse('${latestObs!['price_date']}T00:00:00');
      final weekAgo = latestDate.subtract(const Duration(days: 7));
      final weekAgoStr = weekAgo.toIso8601String().substring(0, 10);
      final cands = (dm.level == MarketLevel.mercado && dm.id != null)
          ? bucket.where((p) =>
              p['market_id'] == dm.id &&
              (p['price_date'] as String).compareTo(weekAgoStr) <= 0).toList()
          : bucket
              .where((p) =>
                  (p['price_date'] as String).compareTo(weekAgoStr) <= 0)
              .toList();
      if (cands.isNotEmpty) {
        final curAvg = (displayMin + displayMax) / 2;
        double prevAvg = 0;
        if (dm.level == MarketLevel.mercado && dm.id != null) {
          final prev = cands.reduce((a, b) =>
              (a['price_date'] as String).compareTo(b['price_date'] as String) > 0
                  ? a
                  : b);
          prevAvg = ((prev['avg_price'] as num?) ??
                  (((prev['min_price'] as num?) ?? 0).toDouble() +
                          ((prev['max_price'] as num?) ?? 0).toDouble()) /
                      2)
              .toDouble();
        } else {
          final prevDate = cands.fold<String>(
              '',
              (a, p) => (p['price_date'] as String).compareTo(a) > 0
                  ? p['price_date'] as String
                  : a);
          final prevDay =
              cands.where((p) => p['price_date'] == prevDate).toList();
          final pMins = <num>[];
          final pMaxs = <num>[];
          for (final p in prevDay) {
            final mn = (p['min_price'] as num?) ?? (p['avg_price'] as num?);
            final mx = (p['max_price'] as num?) ?? (p['avg_price'] as num?);
            if (mn is num && mn > 0) pMins.add(mn);
            if (mx is num && mx > 0) pMaxs.add(mx);
          }
          final pMin = pMins.isEmpty
              ? 0.0
              : pMins.reduce((a, b) => a + b) / pMins.length;
          final pMax = pMaxs.isEmpty
              ? 0.0
              : pMaxs.reduce((a, b) => a + b) / pMaxs.length;
          prevAvg = (pMin + pMax) / 2;
        }
        if (prevAvg > 0 && curAvg > 0) {
          weekChange = pctChange(prevAvg, curAvg);
        }
      }
    }
    return (
      latestObs: latestObs,
      mostCommonPres: mostCommonPres,
      geoSource: geoSource,
      weekChange: weekChange,
      displayMin: displayMin,
      displayMax: displayMax,
    );
  }

  // ── chart data ─────────────────────────────────────────────────────

  List<Map<String, dynamic>> _chartDataFor(List<dynamic> rows) {
    final byDate = <String, Map<String, dynamic>>{};
    for (final p in rows) {
      num? rawMin = ((p['min_price'] as num?) != null && (p['min_price'] as num) > 0)
          ? p['min_price'] as num
          : ((p['avg_price'] as num?) ?? (p['max_price'] as num?));
      num? rawMax = ((p['max_price'] as num?) != null && (p['max_price'] as num) > 0)
          ? p['max_price'] as num
          : ((p['avg_price'] as num?) ?? (p['min_price'] as num?));
      if (rawMin == null || rawMax == null) continue;
      if (rawMin <= 0 && rawMax <= 0) continue;
      final avg = (rawMin + rawMax) / 2;
      final date = p['price_date'] as String;
      final ex = byDate[date];
      if (ex == null) {
        byDate[date] = {
          'date': date,
          'min': rawMin.toDouble(),
          'max': rawMax.toDouble(),
          'avg': avg.toDouble(),
          'count': 1,
        };
      } else {
        ex['min'] = (ex['min'] as double) < rawMin ? ex['min'] : rawMin.toDouble();
        ex['max'] = (ex['max'] as double) > rawMax ? ex['max'] : rawMax.toDouble();
        final c = ex['count'] as int;
        ex['avg'] = ((ex['avg'] as double) * c + avg) / (c + 1);
        ex['count'] = c + 1;
      }
    }
    final out = byDate.values.toList();
    out.sort((a, b) => (a['date'] as String).compareTo(b['date'] as String));
    return out;
  }

  // ── build ──────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    _refreshTimeRanges(context);
    final sp = context.watch<SettingsProvider>();
    final t = sp.t;
    final wl = context.watch<WatchlistProvider>();
    final id = widget.productId;

    final isWatched = wl.isWatched(id);

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        previousPageTitle: t.nav_products,
        middle: Text(
          _product?['canonical_name'] as String? ?? t.nav_product,
          style: const TextStyle(color: AppColors.textInverse),
          overflow: TextOverflow.ellipsis,
        ),
        trailing: _product == null
            ? null
            : CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  context.read<WatchlistProvider>().toggle(
                        id,
                        WatchlistItemType.product,
                        (_product!['canonical_name'] as String?) ?? '',
                      );
                },
                child: Icon(
                  isWatched ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                  color: isWatched
                      ? const Color(0xFFFF6B6B)
                      : AppColors.textInverse,
                  size: 24,
                ),
              ),
      ),
      child: SafeArea(
        bottom: false,
        child: _loading
            ? const Center(child: CupertinoActivityIndicator(radius: 14))
            : _product == null
                ? Center(
                    child: Text(
                      t.product_not_found,
                      style: const TextStyle(
                        fontSize: AppFontSize.md,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  )
                : _buildBody(context, sp),
      ),
    );
  }

  Widget _buildBody(BuildContext context, SettingsProvider sp) {
    final t = sp.t;
    final p = _product!;
    final categoryName = (p['dim_subcategory'] is Map &&
            (p['dim_subcategory'] as Map)['dim_category'] is Map)
        ? ((p['dim_subcategory'] as Map)['dim_category']
            as Map)['canonical_name'] as String?
        : null;
    final subcategoryName = (p['dim_subcategory'] is Map)
        ? (p['dim_subcategory'] as Map)['canonical_name'] as String?
        : null;
    final hi = _headerInfo(sp);
    final headerName = (p['canonical_name'] as String?) ?? '';

    return CustomScrollView(
      slivers: [
        CupertinoSliverRefreshControl(onRefresh: _refresh),
        SliverList(
          delegate: SliverChildListDelegate([
            // ── header ──
            Container(
              padding: const EdgeInsets.all(AppSpacing.lg),
              color: AppColors.surface,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ProductImage(
                    productName: headerName,
                    categoryName: categoryName,
                    size: 80,
                    radius: AppRadius.lg,
                  ),
                  const SizedBox(width: AppSpacing.lg),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          [categoryName, subcategoryName]
                              .where((s) => s != null && s.isNotEmpty)
                              .join(' > ')
                              .toUpperCase(),
                          style: const TextStyle(
                            fontSize: AppFontSize.xs,
                            color: AppColors.textTertiary,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          headerName,
                          style: const TextStyle(
                            fontSize: AppFontSize.xl,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        if (hi.latestObs != null) ...[
                          const SizedBox(height: 4),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              Flexible(
                                child: Text(
                                  hi.displayMax != hi.displayMin
                                      ? '${formatCOP(hi.displayMin)} - ${formatCOP(hi.displayMax)}'
                                      : formatCOP(hi.displayMin),
                                  style: const TextStyle(
                                    fontSize: AppFontSize.md,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.primary,
                                    fontFamily: 'monospace',
                                  ),
                                ),
                              ),
                              const SizedBox(width: AppSpacing.sm),
                              GestureDetector(
                                onTap: () => setState(
                                    () => _showWeekTooltip = !_showWeekTooltip),
                                child: PriceChangeIndicator(
                                  value: hi.weekChange,
                                  size: IndicatorSize.md,
                                ),
                              ),
                            ],
                          ),
                          if (_showWeekTooltip)
                            Container(
                              margin: const EdgeInsets.only(top: 4),
                              padding: const EdgeInsets.symmetric(
                                  horizontal: AppSpacing.sm,
                                  vertical: AppSpacing.xs),
                              decoration: BoxDecoration(
                                color: AppColors.dark,
                                borderRadius:
                                    BorderRadius.circular(AppRadius.sm),
                              ),
                              child: Text(
                                t.product_vs_prev_week,
                                style: const TextStyle(
                                  color: AppColors.textInverse,
                                  fontSize: AppFontSize.xs,
                                ),
                              ),
                            ),
                          const SizedBox(height: 2),
                          Text(
                            [
                              formatDateShort(hi.latestObs!['price_date'] as String),
                              hi.geoSource,
                              hi.mostCommonPres,
                            ].where((s) => s.isNotEmpty).join(' \u00b7 '),
                            style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              color: AppColors.textTertiary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // ── price section ──
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, AppSpacing.xs, AppSpacing.lg, 0),
              child: AppCard(
                child: ExpandableSection(
                  title: t.product_price_section,
                  icon: CupertinoIcons.tag,
                  initiallyExpanded: false,
                  onExpandChange: (open) {
                    setState(() => _priceChartExpanded = open);
                    if (open && _prices.isEmpty) _loadPrices();
                  },
                  child: _buildPriceSection(sp),
                ),
              ),
            ),

            // ── prices by market ──
            if (_marketPrices.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                    AppSpacing.lg, AppSpacing.xs, AppSpacing.lg, 0),
                child: AppCard(
                  child: ExpandableSection(
                    title: t.product_prices_by_market,
                    icon: CupertinoIcons.cart,
                    badge: _marketPriceRows.length,
                    initiallyExpanded: false,
                    child: _buildMarketTable(sp),
                  ),
                ),
              ),

            // ── supply section ──
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, AppSpacing.xs, AppSpacing.lg, 0),
              child: AppCard(
                child: ExpandableSection(
                  title: t.product_supply_section,
                  icon: CupertinoIcons.cube_box,
                  initiallyExpanded: false,
                  onExpandChange: (open) {
                    setState(() => _supplyExpanded = open);
                    if (open) _loadSupply();
                  },
                  child: _buildSupplySection(sp),
                ),
              ),
            ),

            // ── comments ──
            if (sp.settings.commentsEnabled)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                    AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
                child: AppCard(
                  child: CommentsSection(
                    entityType: 'product',
                    entityId: widget.productId,
                  ),
                ),
              ),

            // ── image attribution ──
            if (_imageAttribution != null) _buildImageAttribution(),

            const SizedBox(height: 40),
          ]),
        ),
      ],
    );
  }

  // ── price section ──
  Widget _buildPriceSection(SettingsProvider sp) {
    final t = sp.t;
    final ranges = _availablePriceRangeIdxs;
    if (_timeRangeIdx == null && ranges.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() => _timeRangeIdx = ranges.first);
      });
    } else if (_timeRangeIdx != null && !ranges.contains(_timeRangeIdx)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() => _timeRangeIdx = ranges.isNotEmpty ? ranges.first : null);
      });
    }

    final markets = _availableMarkets;
    final pres = _availablePresentationsFor(_marketFilteredPrices);
    final selectedPres = _selectedPresentation ??
        (pres.isNotEmpty ? pres.first['id'] : null);
    final chartRows = _chartDataFor(_filteredPrices);
    final selectedPresLabel = (pres
            .firstWhere((e) => e['id'] == selectedPres,
                orElse: () => const {'name': ''})['name'] ??
        '') as String;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Time-range tabs
        if (ranges.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: CupertinoSegmentedControl<int>(
                groupValue: _timeRangeIdx,
                padding: EdgeInsets.zero,
                children: {
                  for (final i in ranges)
                    i: Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: AppSpacing.xs),
                      child: Text(_timeRanges[i].label,
                          style: const TextStyle(fontSize: AppFontSize.xs)),
                    )
                },
                onValueChanged: (v) => setState(() => _timeRangeIdx = v),
              ),
            ),
          ),

        // Market chips
        if (markets.isNotEmpty)
          _ChipRow(
            children: [
              _ChipItem(
                label: t.product_national_avg,
                active: _selectedMarketId == null,
                onTap: () => setState(() => _selectedMarketId = null),
              ),
              ...markets.map((m) => _ChipItem(
                    label: m['name']!,
                    active: _selectedMarketId == m['id'],
                    onTap: () => setState(() => _selectedMarketId =
                        _selectedMarketId == m['id'] ? null : m['id']),
                  )),
            ],
          ),

        // Presentation chips
        if (pres.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.xs),
            child: _ChipRow(
              children: pres
                  .map((p) => _ChipItem(
                        label: p['name']!,
                        active:
                            (selectedPres == p['id']) || pres.length == 1,
                        onTap: () => setState(
                            () => _selectedPresentation = p['id']),
                      ))
                  .toList(),
            ),
          ),

        const SizedBox(height: AppSpacing.sm),

        // Chart + stats
        if (chartRows.isNotEmpty) ...[
          if (chartRows.length > 1)
            LayoutBuilder(builder: (ctx, c) => AppLineChart(
              data: chartRows
                  .map((d) => AppLineChartPoint(
                        date: d['date'] as String,
                        value: (d['avg'] as num).toDouble(),
                        min: (d['min'] as num).toDouble(),
                        max: (d['max'] as num).toDouble(),
                      ))
                  .toList(),
              width: c.maxWidth,
              height: 200,
              color: AppColors.primary,
              showBands: true,
              formatValue: formatCOPCompact,
            )),
          const SizedBox(height: AppSpacing.sm),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _Stat(
                label: t.product_min,
                value: formatCOP(chartRows
                    .map((d) => (d['min'] as num).toDouble())
                    .reduce((a, b) => a < b ? a : b)),
              ),
              _Stat(
                label: t.product_avg,
                color: AppColors.primary,
                value: formatCOP(chartRows
                        .map((d) => (d['avg'] as num).toDouble())
                        .reduce((a, b) => a + b) /
                    chartRows.length),
              ),
              _Stat(
                label: t.product_max,
                value: formatCOP(chartRows
                    .map((d) => (d['max'] as num).toDouble())
                    .reduce((a, b) => a > b ? a : b)),
              ),
            ],
          ),
          if (selectedPresLabel.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                selectedPresLabel,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: AppFontSize.xs,
                  color: AppColors.textTertiary,
                ),
              ),
            ),
        ] else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xxl),
            child: Text(
              t.product_no_price_data,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: AppFontSize.sm,
                color: AppColors.textTertiary,
              ),
            ),
          ),
      ],
    );
  }

  // ── prices-by-market table ──
  Widget _buildMarketTable(SettingsProvider sp) {
    final t = sp.t;
    final pres = _availablePresentationsFor(_marketPrices);
    final rows = _marketPriceRows;
    final stats = _mktStats;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          t.product_prices_by_market_note,
          style: const TextStyle(
            fontSize: AppFontSize.xs,
            color: AppColors.textTertiary,
            fontStyle: FontStyle.italic,
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        _ChipRow(
          children: [
            ...pres.map((p) => _ChipItem(
                  label: p['name']!,
                  active: _mktPresFilter == p['id'],
                  onTap: () => setState(() => _mktPresFilter =
                      _mktPresFilter == p['id'] ? null : p['id']),
                )),
            _ChipItem(
              label: _mktSortAsc ? t.product_sort_asc : t.product_sort_desc,
              active: false,
              icon: _mktSortAsc
                  ? CupertinoIcons.arrow_up
                  : CupertinoIcons.arrow_down,
              onTap: () => setState(() => _mktSortAsc = !_mktSortAsc),
            ),
          ],
        ),
        if (rows.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: Container(
                  padding: const EdgeInsets.all(AppSpacing.xs),
                  decoration: BoxDecoration(
                    color: AppColors.accentBlue.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                  ),
                  child: Column(
                    children: [
                      Text(t.product_median,
                          style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              color: AppColors.textTertiary)),
                      Text(formatCOP(stats.median),
                          style: const TextStyle(
                              fontSize: AppFontSize.sm,
                              fontWeight: FontWeight.w600,
                              color: AppColors.accentBlue,
                              fontFamily: 'monospace')),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Container(
                  padding: const EdgeInsets.all(AppSpacing.xs),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                  ),
                  child: Column(
                    children: [
                      Text(t.product_mean,
                          style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              color: AppColors.textTertiary)),
                      Text(formatCOP(stats.mean),
                          style: const TextStyle(
                              fontSize: AppFontSize.sm,
                              fontWeight: FontWeight.w600,
                              color: AppColors.primary,
                              fontFamily: 'monospace')),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
        const SizedBox(height: AppSpacing.sm),
        ...rows.map((p) {
          final ctx = formatPriceContext(
            (p['dim_presentation'] is Map)
                ? (p['dim_presentation'] as Map)['canonical_name'] as String?
                : null,
            (p['dim_units'] is Map)
                ? (p['dim_units'] as Map)['canonical_name'] as String?
                : null,
          );
          final marketLabel = _fmtMarket(p['dim_market']);
          final priceText = (p['max_price'] != p['min_price'])
              ? '${formatCOP(p['min_price'] as num?)} - ${formatCOP(p['max_price'] as num?)}'
              : formatCOP(p['min_price'] as num?);
          return Container(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: AppColors.borderLight),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        marketLabel.isEmpty
                            ? t.product_market_fallback
                            : marketLabel,
                        style: const TextStyle(
                          fontSize: AppFontSize.sm,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      if (ctx.isNotEmpty)
                        Text(ctx,
                            style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              color: AppColors.textTertiary,
                            )),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(priceText,
                        style: const TextStyle(
                          fontSize: AppFontSize.sm,
                          fontWeight: FontWeight.w600,
                          color: AppColors.primary,
                          fontFamily: 'monospace',
                        )),
                    Text(formatDateShort(p['price_date'] as String),
                        style: const TextStyle(
                          fontSize: AppFontSize.xs,
                          color: AppColors.textTertiary,
                        )),
                  ],
                ),
              ],
            ),
          );
        }),
      ],
    );
  }

  // ── supply section ──
  Widget _buildSupplySection(SettingsProvider sp) {
    final t = sp.t;
    final summary = _supplySummary;
    final totalKg = (summary?['total_kg'] as num?)?.toDouble() ?? 0;
    final dailyAvg = (summary?['daily_avg_kg'] as num?)?.toDouble() ?? 0;
    final numDays = (summary?['num_days'] as num?)?.toInt() ?? 0;
    final oldest = summary?['oldest_obs'] as String?;
    final newest = summary?['newest_obs'] as String?;

    final supplyMarkets = _topDestinations
        .map((m) => {
              'id': m['market_id'] as String,
              'name': m['market_name'] as String? ?? '',
            })
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Time-range chips (blue accent)
        _ChipRow(
          children: [
            for (var i = 0; i < _timeRanges.length; i++)
              _ChipItem(
                label: _timeRanges[i].label,
                active: i == _supplyTimeRangeIdx,
                activeColor: AppColors.accentBlue,
                onTap: () {
                  setState(() => _supplyTimeRangeIdx = i);
                  _loadSupply();
                },
              ),
          ],
        ),
        if (_supplyProvFilter != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Align(
              alignment: Alignment.centerLeft,
              child: GestureDetector(
                onTap: () {
                  setState(() => _supplyProvFilter = null);
                  _loadSupply();
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
                  decoration: BoxDecoration(
                    color: AppColors.secondary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(AppRadius.full),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(CupertinoIcons.location,
                          size: 12, color: AppColors.secondary),
                      const SizedBox(width: 4),
                      Text(_supplyProvFilter!,
                          style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              color: AppColors.secondary,
                              fontWeight: FontWeight.w600)),
                      const SizedBox(width: 4),
                      const Icon(CupertinoIcons.clear_circled_solid,
                          size: 14, color: AppColors.secondary),
                    ],
                  ),
                ),
              ),
            ),
          ),
        if (supplyMarkets.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          _ChipRow(
            children: [
              _ChipItem(
                label: t.product_national_avg,
                active: _supplyMarketId == null,
                activeColor: AppColors.accentBlue,
                onTap: () {
                  setState(() => _supplyMarketId = null);
                  _loadSupply();
                },
              ),
              ...supplyMarkets.map((m) => _ChipItem(
                    label: m['name']!,
                    active: _supplyMarketId == m['id'],
                    activeColor: AppColors.accentBlue,
                    onTap: () {
                      setState(() => _supplyMarketId =
                          _supplyMarketId == m['id'] ? null : m['id']);
                      _loadSupply();
                    },
                  )),
            ],
          ),
        ],
        const SizedBox(height: AppSpacing.md),

        // Stat tiles
        Row(
          children: [
            Expanded(
              child: _SupplyTile(
                  value: formatKg(totalKg), label: t.product_total_sum),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: _SupplyTile(
                  value: formatKg(dailyAvg), label: t.product_daily_avg),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('$numDays d',
                style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    color: AppColors.textTertiary)),
            Flexible(
              child: Text(
                [
                  if (oldest != null) formatDateShort(oldest),
                  if (newest != null) formatDateShort(newest),
                ].join(' → '),
                style: const TextStyle(
                    fontSize: AppFontSize.xs, color: AppColors.textTertiary),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),

        // Supply chart (line) by date
        if (_supplyByDate.length > 1)
          LayoutBuilder(builder: (ctx, c) => AppLineChart(
            data: _supplyByDate
                .map((d) => AppLineChartPoint(
                      date: d['date'] as String,
                      value: ((d['kg'] as num?) ?? 0).toDouble(),
                    ))
                .toList(),
            width: c.maxWidth,
            height: 200,
            color: AppColors.accentBlue,
            formatValue: formatKg,
          ))
        else if (_supplyByDate.isEmpty &&
            _topDestinations.isEmpty &&
            _topOrigins.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xxl),
            child: Text(t.product_no_supply_data,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: AppFontSize.sm,
                    color: AppColors.textTertiary)),
          ),

        // Top destinations
        if (_topDestinations.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          const _SupplySubHeader(text: 'Mercados de destino'),
          _SupplyHint(text: t.supply_hint_product_destinations),
          ..._topDestinations.asMap().entries.map((e) {
            final i = e.key;
            final d = e.value;
            final marketId = d['market_id'] as String?;
            final active = _supplyMarketId == marketId;
            final dim = _supplyMarketId != null && !active;
            final maxKg = (_topDestinations.first['total_kg'] as num).toDouble();
            final cur = (d['total_kg'] as num).toDouble();
            return _SupplyBar(
              name: (d['market_name'] as String?) ?? '',
              kg: cur,
              maxKg: maxKg,
              color: active
                  ? AppColors.accentBlue
                  : _supplyColors[i % _supplyColors.length],
              dim: dim,
              activeName: active,
              onTap: () {
                setState(() =>
                    _supplyMarketId = active ? null : marketId);
                _loadSupply();
              },
            );
          }),
        ],

        // Top origins (provenance)
        if (_topOrigins.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _SupplySubHeader(text: t.product_provenance),
          _SupplyHint(text: t.supply_hint_origin_markets),
          ..._topOrigins.asMap().entries.map((e) {
            final i = e.key;
            final d = e.value;
            final dept = (d['dept_name'] as String?) ?? '';
            final active = _supplyProvFilter == dept;
            final dim = _supplyProvFilter != null && !active;
            final maxKg = (_topOrigins.first['total_kg'] as num).toDouble();
            final cur = (d['total_kg'] as num).toDouble();
            return _SupplyBar(
              name: dept,
              kg: cur,
              maxKg: maxKg,
              color:
                  active ? AppColors.secondary : _supplyColors[i % _supplyColors.length],
              dim: dim,
              activeName: active,
              onTap: () {
                setState(() => _supplyProvFilter = active ? null : dept);
                _loadSupply();
              },
            );
          }),
        ],
      ],
    );
  }

  Widget _buildImageAttribution() {
    final attr = _imageAttribution!;
    final author = attr['author'] as String?;
    final source = attr['source_name'] as String? ?? attr['source'] as String?;
    final license = attr['license'] as String?;
    final parts = <String>[
      if (author != null && author.isNotEmpty) author,
      if (source != null && source.isNotEmpty) source,
      if (license != null && license.isNotEmpty) license,
    ];
    if (parts.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, 0),
      child: Text(
        parts.join(' \u00b7 '),
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontSize: AppFontSize.xs,
          color: AppColors.textTertiary,
          fontStyle: FontStyle.italic,
        ),
      ),
    );
  }
}

// ── small private widgets ───────────────────────────────────────────

class _ChipRow extends StatelessWidget {
  final List<Widget> children;
  const _ChipRow({required this.children});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: children,
    );
  }
}

class _ChipItem extends StatelessWidget {
  final String label;
  final bool active;
  final Color activeColor;
  final IconData? icon;
  final VoidCallback onTap;
  const _ChipItem({
    required this.label,
    required this.active,
    required this.onTap,
    this.activeColor = AppColors.primaryDark,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: active ? activeColor : AppColors.surface,
          border: Border.all(
            color: active ? activeColor : AppColors.borderLight,
          ),
          borderRadius: BorderRadius.circular(AppRadius.full),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon,
                  size: 12,
                  color:
                      active ? AppColors.textInverse : AppColors.textSecondary),
              const SizedBox(width: 4),
            ],
            Text(
              label,
              style: TextStyle(
                fontSize: AppFontSize.xs,
                color:
                    active ? AppColors.textInverse : AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  const _Stat({required this.label, required this.value, this.color});
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(
                fontSize: AppFontSize.xs, color: AppColors.textTertiary)),
        Text(value,
            style: TextStyle(
              fontSize: AppFontSize.sm,
              fontWeight: FontWeight.w600,
              color: color ?? AppColors.textPrimary,
              fontFamily: 'monospace',
            )),
      ],
    );
  }
}

class _SupplyTile extends StatelessWidget {
  final String value;
  final String label;
  const _SupplyTile({required this.value, required this.label});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.accentBlue.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                fontSize: AppFontSize.md,
                fontWeight: FontWeight.w700,
                color: AppColors.accentBlue,
              )),
          Text(label,
              style: const TextStyle(
                fontSize: AppFontSize.xs,
                color: AppColors.textSecondary,
              )),
        ],
      ),
    );
  }
}

class _SupplySubHeader extends StatelessWidget {
  final String text;
  const _SupplySubHeader({required this.text});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm, bottom: 2),
      child: Text(text,
          style: const TextStyle(
            fontSize: AppFontSize.sm,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          )),
    );
  }
}

class _SupplyHint extends StatelessWidget {
  final String text;
  const _SupplyHint({required this.text});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs),
      child: Text(text,
          style: const TextStyle(
            fontSize: AppFontSize.xs,
            color: AppColors.textTertiary,
            fontStyle: FontStyle.italic,
          )),
    );
  }
}

class _SupplyBar extends StatelessWidget {
  final String name;
  final double kg;
  final double maxKg;
  final Color color;
  final bool dim;
  final bool activeName;
  final VoidCallback onTap;
  const _SupplyBar({
    required this.name,
    required this.kg,
    required this.maxKg,
    required this.color,
    required this.dim,
    required this.activeName,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final pct = maxKg > 0 ? (kg / maxKg).clamp(0.0, 1.0) : 0.0;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Opacity(
        opacity: dim ? 0.4 : 1.0,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Row(
            children: [
              SizedBox(
                width: 100,
                child: Text(
                  name,
                  textAlign: TextAlign.right,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppFontSize.xs,
                    fontWeight:
                        activeName ? FontWeight.w700 : FontWeight.w400,
                    color: activeName ? color : AppColors.textSecondary,
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Container(
                  height: 16,
                  decoration: BoxDecoration(
                    color: AppColors.borderLight,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: pct,
                    child: Container(
                      decoration: BoxDecoration(
                        color: color,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              SizedBox(
                width: 60,
                child: Text(
                  formatKg(kg),
                  style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}


