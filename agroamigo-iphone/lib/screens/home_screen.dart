import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import 'package:agroamigo_iphone/api/comments_api.dart';
import 'package:agroamigo_iphone/api/insumos_api.dart';
import 'package:agroamigo_iphone/api/markets_api.dart';
import 'package:agroamigo_iphone/api/products_api.dart';
import 'package:agroamigo_iphone/api/supply_api.dart';
import 'package:agroamigo_iphone/services/format.dart';
import 'package:agroamigo_iphone/services/images.dart';
import 'package:agroamigo_iphone/state/settings_provider.dart';
import 'package:agroamigo_iphone/state/watchlist_provider.dart';
import 'package:agroamigo_iphone/theme/theme.dart';
import 'package:agroamigo_iphone/translations/dim_name.dart';
import 'package:agroamigo_iphone/translations/translations.dart';
import 'package:agroamigo_iphone/widgets/card.dart';
import 'package:agroamigo_iphone/widgets/price_change_indicator.dart';
import 'package:agroamigo_iphone/widgets/section_header.dart';
import 'package:agroamigo_iphone/widgets/sparkline.dart';

import 'insumo_detail_screen.dart';
import 'market_detail_screen.dart';
import 'product_detail_screen.dart';
import 'products_screen.dart';

/// Mirror of `CATEGORY_ICONS` in the RN home screen — closest Cupertino
/// equivalents per the porting brief.
const Map<String, IconData> _categoryIcons = {
  'Frutas': CupertinoIcons.heart_solid,
  'Verduras y hortalizas': CupertinoIcons.leaf_arrow_circlepath,
  'Tubérculos, raíces y plátanos': CupertinoIcons.globe,
  'Carnes': CupertinoIcons.cart,
  'Pescados': CupertinoIcons.hare,
  'Granos y cereales': CupertinoIcons.square_grid_2x2,
  'Procesados': CupertinoIcons.cube_box,
  'Lácteos y huevos': CupertinoIcons.drop,
};

class _Trending {
  final String name;
  final List<num> prices;
  final String productId;
  final String presentation;
  final String market;
  final double change;
  final num latestPrice;

  _Trending({
    required this.name,
    required this.prices,
    required this.productId,
    required this.presentation,
    required this.market,
    required this.change,
    required this.latestPrice,
  });
}

class _MarketSupply {
  final String id;
  final String name;
  final num kg;
  final String? date;
  _MarketSupply({required this.id, required this.name, required this.kg, this.date});
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Map<String, dynamic>> _categories = [];
  List<_Trending> _trending = [];
  List<Map<String, dynamic>> _topSupplied = [];
  List<_MarketSupply> _marketTopSupplied = [];
  String _trendingScope = 'national'; // 'market' | 'national'
  Map<String, Map<String, dynamic>> _watchlistPrices = {};
  Map<String, Map<String, dynamic>> _insumoWatchlistPrices = {};
  List<Map<String, dynamic>> _latestComments = [];
  bool _loading = true;

  // Track the inputs we last loaded with, so didChangeDependencies can
  // re-fire `loadData` / `loadWatchlistPrices` when they change — mirrors
  // the RN useEffect dependency arrays.
  String? _lastMarketKey;
  int? _lastWatchlistHash;

  @override
  void initState() {
    super.initState();
    // Defer initial loads to the first frame so context.read works.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _maybeReload();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _maybeReload();
  }

  void _maybeReload() {
    final settings = context.read<SettingsProvider>().settings;
    final wl = context.read<WatchlistProvider>().items;
    final marketKey =
        '${settings.defaultMarket.level.name}|${settings.defaultMarket.id ?? ''}';
    final wlHash = Object.hashAll(wl.map((i) => '${i.type.name}:${i.id}'));

    if (_lastMarketKey != marketKey) {
      _lastMarketKey = marketKey;
      _loadData();
      _loadWatchlistPrices();
      _lastWatchlistHash = wlHash;
    } else if (_lastWatchlistHash != wlHash) {
      _lastWatchlistHash = wlHash;
      _loadWatchlistPrices();
    }
  }

  Future<void> _loadWatchlistPrices() async {
    final settings = context.read<SettingsProvider>().settings;
    final wl = context.read<WatchlistProvider>().items;
    final productIds = wl
        .where((i) => i.type == WatchlistItemType.product)
        .map((i) => i.id)
        .toList();
    final insumoIds = wl
        .where((i) => i.type == WatchlistItemType.insumo)
        .map((i) => i.id)
        .toList();
    final preferredMarketId = settings.defaultMarket.level == MarketLevel.mercado
        ? settings.defaultMarket.id
        : null;

    if (!mounted) return;
    setState(() => _watchlistPrices = {});

    if (productIds.isNotEmpty) {
      try {
        final data =
            await getWatchlistPrices(productIds, marketId: preferredMarketId);
        final map = <String, Map<String, dynamic>>{};
        for (final obs in data) {
          final pid = obs['product_id'] as String?;
          if (pid != null && !map.containsKey(pid)) map[pid] = obs;
        }
        if (mounted) setState(() => _watchlistPrices = map);
      } catch (e) {
        // ignore: avoid_print
        print('watchlist prices: $e');
      }
    }

    if (insumoIds.isNotEmpty) {
      try {
        final data = await getWatchlistInsumoPrices(insumoIds);
        final map = <String, Map<String, dynamic>>{};
        for (final obs in data) {
          final iid = obs['insumo_id'] as String?;
          if (iid != null && !map.containsKey(iid)) map[iid] = obs;
        }
        if (mounted) setState(() => _insumoWatchlistPrices = map);
      } catch (e) {
        // ignore: avoid_print
        print('insumo watchlist prices: $e');
      }
    } else {
      if (mounted) setState(() => _insumoWatchlistPrices = {});
    }
  }

  Future<void> _loadData() async {
    final settings = context.read<SettingsProvider>().settings;
    final t = context.read<SettingsProvider>().t;

    if (!mounted) return;
    setState(() {
      _trending = [];
      _marketTopSupplied = [];
    });

    final preferredMarketId =
        settings.defaultMarket.level == MarketLevel.mercado
            ? settings.defaultMarket.id
            : null;

    // Independent fetches — slow/failed endpoints don't block others.
    getCategories().then((c) {
      if (mounted) setState(() => _categories = List<Map<String, dynamic>>.from(c));
    }).catchError((e) {
      // ignore: avoid_print
      print('categories: $e');
    });

    getTopSuppliedProducts(limit: 10).then((s) {
      if (mounted) {
        setState(() => _topSupplied = List<Map<String, dynamic>>.from(s));
      }
    }).catchError((_) {});

    getLatestComments(limit: 10).then((c) {
      if (mounted) {
        setState(() => _latestComments = List<Map<String, dynamic>>.from(c));
      }
    }).catchError((_) {});

    if (settings.defaultMarket.level == MarketLevel.mercado &&
        settings.defaultMarket.id != null) {
      getMarketTopProducts(settings.defaultMarket.id!, 7, limit: 8).then((rows) {
        if (!mounted) return;
        setState(() {
          _marketTopSupplied = rows
              .map((r) => _MarketSupply(
                    id: (r['product_id'] as String?) ?? '',
                    name: (r['product_name'] as String?) ?? t.market_product_fallback,
                    kg: (r['total_kg'] as num?) ?? 0,
                    date: r['newest_obs'] as String?,
                  ))
              .toList();
        });
      }).catchError((_) {
        if (mounted) setState(() => _marketTopSupplied = []);
      });
    }

    try {
      // Try the default market first. If the mercado scope has too few
      // observations to compute trends (<10 rows), fall back to national.
      // National scope pulls the PostgREST max (1000 rows) so we have
      // enough cross-market samples per (product, presentation).
      const marketLimit = 200;
      const nationalLimit = 1000;
      var trend = await getTrendingProducts(
        limit: preferredMarketId != null ? marketLimit : nationalLimit,
        marketId: preferredMarketId,
      );
      var trendScope = preferredMarketId != null ? 'market' : 'national';
      if (preferredMarketId != null && trend.length < 10) {
        trend = await getTrendingProducts(limit: nationalLimit);
        trendScope = 'national';
      }

      // Aggregation key: include market_id only when we're scoped to a
      // single market (mercado level). For national scope, keying by
      // (product, presentation) lets observations from different markets
      // feed the same bucket so prices.length >= 2 actually matches.
      final scopedByMarket = trendScope == 'market';
      final productMap = <String, Map<String, dynamic>>{};
      for (final obs in trend) {
        final productId = (obs['product_id'] as String?) ?? '';
        final presentationId = (obs['presentation_id'] as String?) ?? '';
        final marketId = (obs['market_id'] as String?) ?? '';
        final key = scopedByMarket
            ? '$productId|$presentationId|$marketId'
            : '$productId|$presentationId';
        final name = (obs['dim_product'] as Map?)?['canonical_name']
                as String? ??
            'Unknown';
        final presentation = (obs['dim_presentation'] as Map?)?['canonical_name']
                as String? ??
            '';
        // In national scope we aggregate across markets, so stash
        // "(varios)" rather than pinning to one market's name.
        final market = scopedByMarket
            ? ((obs['dim_market'] as Map?)?['canonical_name'] as String? ?? '')
            : t.product_national_avg;
        final price = (obs['avg_price'] as num?) ??
            (obs['max_price'] as num?) ??
            (obs['min_price'] as num?) ??
            0;
        final entry = productMap.putIfAbsent(
          key,
          () => {
            'name': name,
            'prices': <num>[],
            'productId': productId,
            'presentation': presentation,
            'market': market,
          },
        );
        (entry['prices'] as List<num>).add(price);
      }

      final all = productMap.values
          .where((p) => (p['prices'] as List).length >= 2)
          .map((p) {
        final prices = p['prices'] as List<num>;
        final oldest = prices[prices.length - 1];
        final newest = prices[0];
        return _Trending(
          name: p['name'] as String,
          prices: List<num>.from(prices),
          productId: p['productId'] as String,
          presentation: p['presentation'] as String,
          market: p['market'] as String,
          change: pctChange(oldest, newest),
          latestPrice: newest,
        );
      }).toList()
        ..sort((a, b) => b.change.abs().compareTo(a.change.abs()));

      // Keep only the single biggest-move entry per product — otherwise
      // the same product fills the list multiple times with different
      // markets/presentations.
      final seen = <String>{};
      final list = <_Trending>[];
      for (final p in all) {
        if (seen.contains(p.productId)) continue;
        seen.add(p.productId);
        list.add(p);
        if (list.length >= 15) break;
      }

      if (mounted) {
        setState(() {
          _trendingScope = trendScope;
          _trending = list;
        });
      }
    } catch (e) {
      // ignore: avoid_print
      print('Error loading home data: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    await Future.wait([_loadData(), _loadWatchlistPrices()]);
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>().settings;
    final t = context.watch<SettingsProvider>().t;
    final wl = context.watch<WatchlistProvider>();
    final scale = settings.fontSizeScale;

    if (_loading) {
      return Container(
        color: AppColors.background,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CupertinoActivityIndicator(radius: 14),
              const SizedBox(height: AppSpacing.md),
              Text(
                t.home_loading,
                style: TextStyle(
                  fontSize: AppFontSize.md * scale,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      );
    }

    final topMoversUp =
        _trending.where((tr) => tr.change > 0).take(5).toList();
    final topMoversDown = _trending.where((tr) => tr.change < 0).toList()
      ..sort((a, b) => a.change.compareTo(b.change));
    final topMoversDownTrim = topMoversDown.take(5).toList();

    final scopeSuffix = _trendingScope == 'market'
        ? ' — ${settings.defaultMarket.displayName(t)}'
        : ' — ${t.product_national_avg}';

    return Container(
      color: AppColors.background,
      child: CustomScrollView(
        slivers: [
          CupertinoSliverRefreshControl(onRefresh: _refresh),
          SliverToBoxAdapter(child: _buildTicker(t, scale)),
          SliverToBoxAdapter(child: _buildMarketBanner(settings, t, scale)),
          if (wl.items.isNotEmpty) ...[
            SliverToBoxAdapter(child: SectionHeader(title: t.home_watchlist)),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) =>
                    _buildWatchlistCard(wl.items[idx], wl, t, scale),
                childCount: wl.items.length,
              ),
            ),
          ],
          SliverToBoxAdapter(child: SectionHeader(title: t.home_categories)),
          SliverToBoxAdapter(child: _buildCategoryGrid(scale, settings.locale)),
          if (topMoversUp.isNotEmpty) ...[
            SliverToBoxAdapter(
              child: SectionHeader(
                  title: '${t.home_top_increases}$scopeSuffix'),
            ),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) => _buildTrendingCard(topMoversUp[idx], t, scale),
                childCount: topMoversUp.length,
              ),
            ),
          ],
          if (topMoversDownTrim.isNotEmpty) ...[
            SliverToBoxAdapter(
              child: SectionHeader(
                  title: '${t.home_top_decreases}$scopeSuffix'),
            ),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) =>
                    _buildTrendingCard(topMoversDownTrim[idx], t, scale),
                childCount: topMoversDownTrim.length,
              ),
            ),
          ],
          if (_marketTopSupplied.isNotEmpty) ...[
            SliverToBoxAdapter(
              child: SectionHeader(
                  title:
                      '${t.home_top_supply} — ${settings.defaultMarket.displayName(t)}'),
            ),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) =>
                    _buildMarketSupplyCard(_marketTopSupplied[idx], t, scale),
                childCount: _marketTopSupplied.length,
              ),
            ),
          ],
          if (_marketTopSupplied.isEmpty && _topSupplied.isNotEmpty) ...[
            SliverToBoxAdapter(
              child: SectionHeader(
                  title:
                      '${t.home_top_supply} — ${t.product_national_avg}'),
            ),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) =>
                    _buildNationalSupplyCard(_topSupplied[idx], t, scale),
                childCount: _topSupplied.length,
              ),
            ),
          ],
          if (settings.commentsEnabled && _latestComments.isNotEmpty) ...[
            SliverToBoxAdapter(child: SectionHeader(title: t.comments_latest)),
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (ctx, idx) =>
                    _buildCommentCard(_latestComments[idx], t, scale),
                childCount: _latestComments.length,
              ),
            ),
          ],
          SliverToBoxAdapter(child: _buildHelpButton(t, scale)),
          const SliverToBoxAdapter(child: SizedBox(height: 20)),
        ],
      ),
    );
  }

  // ----- Section builders -----

  Widget _buildTicker(dynamic t, double scale) {
    final items = _trending.take(8).toList();
    return Container(
      color: AppColors.dark,
      constraints: const BoxConstraints(maxHeight: 56),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.sm),
        child: Row(
          children: [
            for (final item in items)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.lg),
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => _pushProduct(item.productId),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 80),
                        child: Text(
                          item.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: AppColors.textInverse,
                            fontSize: AppFontSize.sm * scale,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      Text(
                        formatCOPCompact(item.latestPrice),
                        style: TextStyle(
                          color: AppColors.textInverse,
                          fontSize: AppFontSize.sm * scale,
                          fontFamily: 'Menlo',
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      PriceChangeIndicator(value: item.change, size: IndicatorSize.sm),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildMarketBanner(AppSettings settings, dynamic t, double scale) {
    final isNational = settings.defaultMarket.level == MarketLevel.nacional;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.sm),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _showMarketInfo(settings, scale),
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.md),
            border: Border.all(color: AppColors.borderLight),
          ),
          child: Row(
            children: [
              Icon(
                isNational ? CupertinoIcons.globe : CupertinoIcons.cart_fill,
                size: 16,
                color: isNational ? AppColors.accentBlue : AppColors.primary,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  settings.defaultMarket.displayName(t),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppFontSize.sm * scale,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              const Icon(CupertinoIcons.info_circle,
                  size: 18, color: AppColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWatchlistCard(
      WatchlistItem item, WatchlistProvider wl, dynamic t, double scale) {
    final isProduct = item.type == WatchlistItemType.product;
    final priceData =
        isProduct ? _watchlistPrices[item.id] : _insumoWatchlistPrices[item.id];

    String ctx = '';
    if (priceData != null) {
      if (isProduct) {
        ctx = formatPriceContext(
          (priceData['dim_presentation'] as Map?)?['canonical_name']
              as String?,
          (priceData['dim_units'] as Map?)?['canonical_name'] as String?,
        );
      } else {
        ctx = (priceData['presentation'] as String?) ?? '';
      }
    }

    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm / 2),
      child: AppCard(
        onPressed: () {
          if (isProduct) {
            _pushProduct(item.id);
          } else {
            _pushInsumo(item.id);
          }
        },
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppRadius.md),
                color: (isProduct ? AppColors.primary : AppColors.secondary)
                    .withValues(alpha: 0.08),
              ),
              alignment: Alignment.center,
              child: Icon(
                isProduct ? CupertinoIcons.tag : CupertinoIcons.lab_flask,
                size: 16,
                color: isProduct ? AppColors.primary : AppColors.secondary,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  if (priceData != null) ...[
                    Text(
                      _watchlistPriceLabel(priceData),
                      style: TextStyle(
                        fontSize: AppFontSize.sm * scale,
                        fontWeight: FontWeight.w600,
                        color:
                            isProduct ? AppColors.primary : AppColors.secondary,
                        fontFamily: 'Menlo',
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _watchlistMetaLabel(priceData, isProduct, ctx, t),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ] else ...[
                    Text(
                      t.home_no_recent_data,
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            CupertinoButton(
              padding: const EdgeInsets.all(AppSpacing.xs),
              minSize: 0,
              onPressed: () => wl.remove(item.id),
              child: const Icon(CupertinoIcons.clear_circled_solid,
                  size: 20, color: AppColors.textTertiary),
            ),
          ],
        ),
      ),
    );
  }

  String _watchlistPriceLabel(Map<String, dynamic> priceData) {
    final avgOrMin = priceData['avg_price'] ?? priceData['min_price'];
    final maxP = priceData['max_price'];
    final minP = priceData['min_price'];
    final hasRange = maxP != null && maxP != minP;
    return '${formatCOP(avgOrMin as num?)}${hasRange ? ' - ${formatCOP(maxP as num?)}' : ''}';
  }

  String _watchlistMetaLabel(
      Map<String, dynamic> priceData, bool isProduct, String ctx, dynamic t) {
    final dateRaw = priceData['price_date'] as String?;
    final parts = <String>[];
    if (dateRaw != null && dateRaw.isNotEmpty) {
      parts.add(formatDateShort(dateRaw));
    }
    if (isProduct) {
      final fromDefault = priceData['_from_default'] as bool? ?? false;
      final marketName =
          (priceData['dim_market'] as Map?)?['canonical_name'] as String?;
      final label = fromDefault && marketName != null
          ? marketName
          : t.product_national_avg as String;
      if (label.isNotEmpty) parts.add(label);
    } else {
      final dept = (priceData['dim_department'] as Map?)?['canonical_name']
          as String?;
      if (dept != null && dept.isNotEmpty) parts.add(dept);
    }
    if (ctx.isNotEmpty) parts.add(ctx);
    return parts.join(' · ');
  }

  Widget _buildCategoryGrid(double scale, AppLocale locale) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: LayoutBuilder(
        builder: (context, constraints) {
          const gap = AppSpacing.sm;
          final tileW = (constraints.maxWidth - gap) / 2;
          return Wrap(
            spacing: gap,
            runSpacing: gap,
            children: [
              for (final cat in _categories)
                SizedBox(
                  width: tileW,
                  height: 100,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () {
                      Navigator.of(context).push(
                        CupertinoPageRoute(
                          builder: (_) => ProductsScreen(
                              categoryId: cat['id'] as String?),
                        ),
                      );
                    },
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(AppRadius.lg),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          CachedNetworkImage(
                            imageUrl: getCategoryImageUrl(
                                cat['canonical_name'] as String? ?? ''),
                            fit: BoxFit.cover,
                            errorWidget: (_, __, ___) => Container(
                                color: AppColors.darkSurface),
                            placeholder: (_, __) =>
                                Container(color: AppColors.darkSurface),
                          ),
                          Container(
                            color: const Color(0x99162E1A),
                            padding: const EdgeInsets.all(AppSpacing.sm),
                            alignment: Alignment.center,
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  _categoryIcons[
                                          cat['canonical_name'] as String? ??
                                              ''] ??
                                      CupertinoIcons.leaf_arrow_circlepath,
                                  size: 22,
                                  color: AppColors.textInverse,
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  dimDisplayName(cat as Map?, locale),
                                  textAlign: TextAlign.center,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    color: AppColors.textInverse,
                                    fontSize: AppFontSize.sm * scale,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildTrendingCard(_Trending item, dynamic t, double scale) {
    final subtitleParts = <String>[];
    if (item.presentation.isNotEmpty) subtitleParts.add(item.presentation);
    if (item.market.isNotEmpty) subtitleParts.add(item.market);
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm / 2),
      child: AppCard(
        onPressed: () => _pushProduct(item.productId),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (subtitleParts.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitleParts.join(' \u00b7 '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppFontSize.xs * scale,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ],
                  const SizedBox(height: 2),
                  Text(
                    formatCOP(item.latestPrice),
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      color: AppColors.textSecondary,
                      fontFamily: 'Menlo',
                    ),
                  ),
                  Text(
                    t.home_last_7_days,
                    style: TextStyle(
                      fontSize: AppFontSize.xs * scale,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Sparkline(
                  data: item.prices.reversed
                      .map((n) => n.toDouble())
                      .toList(),
                  width: 50,
                  height: 20,
                ),
                const SizedBox(height: 4),
                PriceChangeIndicator(value: item.change, size: IndicatorSize.sm),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMarketSupplyCard(_MarketSupply item, dynamic t, double scale) {
    final dateLabel = item.date != null && item.date!.isNotEmpty
        ? formatDateShort(item.date!)
        : null;
    final subtitle = [t.home_last_week, dateLabel]
        .where((s) => s != null && (s as String).isNotEmpty)
        .join(' \u00b7 ');
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm / 2),
      child: AppCard(
        onPressed: () => _pushProduct(item.id),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppRadius.md),
                color: AppColors.accentBlue.withValues(alpha: 0.08),
              ),
              alignment: Alignment.center,
              child: const Icon(CupertinoIcons.cube_box,
                  size: 16, color: AppColors.accentBlue),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: AppFontSize.xs * scale,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
            Text(
              formatKg(item.kg),
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                fontWeight: FontWeight.w700,
                color: AppColors.accentBlue,
                fontFamily: 'Menlo',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNationalSupplyCard(
      Map<String, dynamic> item, dynamic t, double scale) {
    final newest = item['newest_obs'] as String?;
    final dateLabel =
        newest != null && newest.isNotEmpty ? formatDateShort(newest) : null;
    final subtitle = [t.home_last_week, dateLabel]
        .where((s) => s != null && (s as String).isNotEmpty)
        .join(' \u00b7 ');
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm / 2),
      child: AppCard(
        onPressed: () => _pushProduct(item['product_id'] as String? ?? ''),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppRadius.md),
                color: AppColors.accentBlue.withValues(alpha: 0.08),
              ),
              alignment: Alignment.center,
              child: const Icon(CupertinoIcons.cube_box,
                  size: 16, color: AppColors.accentBlue),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    (item['name'] as String?) ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: AppFontSize.xs * scale,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
            Text(
              formatKg(item['total_kg'] as num?),
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                fontWeight: FontWeight.w700,
                color: AppColors.accentBlue,
                fontFamily: 'Menlo',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCommentCard(
      Map<String, dynamic> c, dynamic t, double scale) {
    final entityName = c['entity_name'] as String?;
    final entityType = c['entity_type'] as String?;
    final entityLabel = entityName != null && entityName.isNotEmpty
        ? '${t.comments_on} $entityName'
        : entityType == 'product'
            ? t.comments_on_product
            : entityType == 'market'
                ? t.comments_on_market
                : t.comments_on_insumo;

    final createdAt = (c['created_at'] as String?) ?? '';
    DateTime? ts;
    try {
      ts = DateTime.parse(createdAt);
    } catch (_) {}
    String dateStr = '';
    String timeStr = '';
    if (ts != null) {
      final datePart = createdAt.split('T').first;
      try {
        dateStr = formatDateShort(datePart);
      } catch (_) {}
      timeStr =
          '${ts.hour.toString().padLeft(2, '0')}:${ts.minute.toString().padLeft(2, '0')}';
    }

    final username =
        (c['profiles'] as Map?)?['username'] as String? ?? '?';

    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm / 2),
      child: AppCard(
        onPressed: () {
          final id = c['entity_id'] as String?;
          if (id == null) return;
          if (entityType == 'insumo') {
            _pushInsumo(id);
          } else if (entityType == 'market') {
            Navigator.of(context).push(
              CupertinoPageRoute(
                  builder: (_) => MarketDetailScreen(marketId: id)),
            );
          } else {
            _pushProduct(id);
          }
        },
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(CupertinoIcons.person_circle,
                size: 24, color: AppColors.textTertiary),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: AppSpacing.xs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        username,
                        style: TextStyle(
                          fontSize: AppFontSize.sm * scale,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      Text(
                        entityLabel,
                        style: TextStyle(
                          fontSize: AppFontSize.xs * scale,
                          color: AppColors.textTertiary,
                        ),
                      ),
                      Text(
                        '$dateStr $timeStr',
                        style: TextStyle(
                          fontSize: AppFontSize.xs * scale,
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    (c['content'] as String?) ?? '',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHelpButton(dynamic t, double scale) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, 0),
      child: Container(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppColors.border, width: 0.5)),
        ),
        child: CupertinoButton(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
          onPressed: () => _showMethodology(t, scale),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(CupertinoIcons.question_circle,
                  size: 20, color: AppColors.textSecondary),
              const SizedBox(width: AppSpacing.sm),
              Text(
                t.home_help_methodology,
                style: TextStyle(
                  fontSize: AppFontSize.sm * scale,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ----- Modals -----

  void _showMarketInfo(AppSettings settings, double scale) {
    final t = context.read<SettingsProvider>().t;
    final levelBlurb = settings.defaultMarket.level == MarketLevel.nacional
        ? t.home_market_info_blurb_nacional
        : settings.defaultMarket.level == MarketLevel.departamento
            ? t.home_market_info_blurb_departamento
            : settings.defaultMarket.level == MarketLevel.ciudad
                ? t.home_market_info_blurb_ciudad
                : t.home_market_info_blurb_mercado;

    showCupertinoDialog(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => CupertinoAlertDialog(
        title: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(CupertinoIcons.info_circle_fill,
                size: 22, color: AppColors.primary),
            const SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Text(
                t.home_market_info_title,
                style: TextStyle(
                  fontSize: AppFontSize.lg * scale,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: AppSpacing.sm),
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: '${t.home_market_info_text} '),
                  TextSpan(
                    text: settings.defaultMarket.displayName(t),
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const TextSpan(text: '.'),
                ],
              ),
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              levelBlurb,
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: '${t.home_market_info_change} '),
                  TextSpan(
                    text: t.nav_settings,
                    style: const TextStyle(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const TextSpan(text: '.'),
                ],
              ),
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md, vertical: AppSpacing.sm),
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(AppRadius.sm),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _legendRow(AppColors.primary,
                      t.home_market_legend_selected, scale),
                  const SizedBox(height: AppSpacing.sm),
                  _legendRow(
                      AppColors.accentBlue,
                      t.home_market_legend_fallback,
                      scale),
                ],
              ),
            ),
          ],
        ),
        actions: [
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(t.home_understood),
          ),
        ],
      ),
    );
  }

  Widget _legendRow(Color color, String label, double scale) {
    return Row(
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: AppSpacing.sm),
        Flexible(
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppFontSize.xs * scale,
              color: AppColors.textSecondary,
            ),
          ),
        ),
      ],
    );
  }

  void _showMethodology(dynamic t, double scale) {
    Navigator.of(context, rootNavigator: true).push(
      CupertinoPageRoute(
        fullscreenDialog: true,
        builder: (_) => _MethodologyModal(t: t, scale: scale),
      ),
    );
  }

  // ----- Navigation helpers -----

  void _pushProduct(String id) {
    if (id.isEmpty) return;
    Navigator.of(context).push(
      CupertinoPageRoute(
        builder: (_) => ProductDetailScreen(productId: id),
      ),
    );
  }

  void _pushInsumo(String id) {
    if (id.isEmpty) return;
    Navigator.of(context).push(
      CupertinoPageRoute(
        builder: (_) => InsumoDetailScreen(insumoId: id),
      ),
    );
  }
}

class _MethodologyModal extends StatelessWidget {
  final dynamic t;
  final double scale;
  const _MethodologyModal({required this.t, required this.scale});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: AppColors.background,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.surface,
        middle: Text(t.home_help,
            style: TextStyle(
              fontSize: AppFontSize.lg * scale,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            )),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => Navigator.of(context).pop(),
          child: const Icon(CupertinoIcons.xmark,
              size: 22, color: AppColors.textPrimary),
        ),
      ),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg, AppSpacing.md, AppSpacing.lg, 40),
          children: [
            _sectionTitle(t.home_app_guide),
            _helpItem(CupertinoIcons.home, t.nav_home_tab,
                t.home_help_home_text),
            _helpItem(CupertinoIcons.tag, t.nav_products,
                t.home_help_products_text),
            _helpItem(CupertinoIcons.cart, t.nav_markets,
                t.home_help_markets_text),
            _helpItem(CupertinoIcons.lab_flask, t.nav_inputs,
                t.home_help_inputs_text),
            _helpItem(
                CupertinoIcons.map, t.nav_map, t.home_help_map_text),
            const SizedBox(height: AppSpacing.lg),
            Container(height: 0.5, color: AppColors.border),
            const SizedBox(height: AppSpacing.lg),
            _sectionTitle(t.home_sources_methodology),
            _heading('Fuente de datos'),
            _body(t.home_sources_text),
            _heading('Precios mayoristas'),
            _body(
                'Publicados diariamente en boletines PDF por mercado. Incluyen precios mínimo y máximo en dos rondas de negociación. Cubren 43 mercados en 23 ciudades desde junio de 2012. Los documentos escaneados se procesan mediante OCR con inteligencia artificial.'),
            _heading('Abastecimiento'),
            _body(
                'Registran los kilogramos de alimentos que ingresan diariamente a los mercados mayoristas, con departamento y municipio de origen. Disponibles desde 2013 para 18 mercados.'),
            _heading('Insumos agropecuarios'),
            _body(
                'Precios promedio mensuales a nivel de municipio y departamento. Incluyen marca comercial y código CPC. Disponibles desde 2013.'),
            _heading('Leche y arroz'),
            _body(
                'Precios mensuales de leche cruda en finca (por litro) y arroz en molino (por tonelada), por municipio. Desde 2013.'),
            _heading('Procesamiento y normalización'),
            _body(
                'Los datos se extraen automáticamente de los archivos del DANE, se normalizan para unificar variaciones en nombres de productos, mercados y presentaciones, y se almacenan con identificadores únicos para seguimiento consistente. Cada producto se clasifica por categoría, subcategoría y código CPC.'),
            _heading('Frecuencia de actualización'),
            _body(
                'Precios mayoristas: diaria. Abastecimiento: diaria (publicación mensual). Leche, arroz e insumos: mensual.'),
            const SizedBox(height: AppSpacing.lg),
            Opacity(
              opacity: 0.7,
              child: Text(
                t.home_disclaimer,
                style: TextStyle(
                  fontSize: AppFontSize.sm * scale,
                  color: AppColors.textSecondary,
                  fontStyle: FontStyle.italic,
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(String text) => Padding(
        padding: const EdgeInsets.only(
            top: AppSpacing.md, bottom: AppSpacing.md),
        child: Text(
          text,
          style: TextStyle(
            fontSize: AppFontSize.lg * scale,
            fontWeight: FontWeight.w700,
            color: AppColors.primary,
          ),
        ),
      );

  Widget _helpItem(IconData icon, String title, String body) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.lg),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 20, color: AppColors.primary),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppFontSize.md * scale,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    body,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      color: AppColors.textSecondary,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _heading(String text) => Padding(
        padding: const EdgeInsets.only(
            top: AppSpacing.lg, bottom: AppSpacing.xs),
        child: Text(
          text,
          style: TextStyle(
            fontSize: AppFontSize.md * scale,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
      );

  Widget _body(String text) => Text(
        text,
        style: TextStyle(
          fontSize: AppFontSize.sm * scale,
          color: AppColors.textSecondary,
          height: 1.4,
        ),
      );
}

