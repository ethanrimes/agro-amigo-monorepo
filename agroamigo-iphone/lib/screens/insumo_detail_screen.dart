import 'package:cached_network_image/cached_network_image.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/image_attribution_api.dart';
import '../api/insumos_api.dart' as insumos_api;
import '../services/cache.dart';
import '../services/format.dart';
import '../services/images.dart';
import '../state/settings_provider.dart';
import '../state/watchlist_provider.dart';
import '../theme/theme.dart';
import '../translations/translations.dart';
import '../widgets/card.dart';
import '../widgets/comments_section.dart';
import '../widgets/expandable_section.dart';

/// Insumo (agricultural input) detail. Mirrors
/// `agroamigo-app/app/insumo/[id].tsx`.
class InsumoDetailScreen extends StatefulWidget {
  final String insumoId;
  const InsumoDetailScreen({super.key, required this.insumoId});

  @override
  State<InsumoDetailScreen> createState() => _InsumoDetailScreenState();
}

enum _PriceSeries { department, municipality }

class _TimeRange {
  final String label;
  final int days; // 0 = all
  const _TimeRange(this.label, this.days);
}

class _InsumoDetailScreenState extends State<InsumoDetailScreen> {
  Map<String, dynamic>? _insumo;
  bool _loading = true;
  bool _notFound = false;

  // Series data (lazily fetched once chart expands).
  List<Map<String, dynamic>> _deptPrices = [];
  List<Map<String, dynamic>> _muniPrices = [];
  bool _pricesLoaded = false;

  _PriceSeries _series = _PriceSeries.department;
  String? _chartPresentation;
  String? _chartDept;
  int? _timeRangeIndex;

  // Municipality tab filter (department dropdown for the muni list).
  String? _muniListDeptFilter;
  bool _sortAsc = false;

  // Image attribution.
  ImageAttribution? _attribution;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final ins = await AppCache.instance.cachedCall<Map<String, dynamic>>(
        'insumo:${widget.insumoId}:entity',
        () => insumos_api.getInsumoById(widget.insumoId),
      );
      if (!mounted) return;
      setState(() {
        _insumo = ins;
        _loading = false;
      });
      _loadPrices();
      _loadAttribution(ins);
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
          _notFound = true;
        });
      }
    }
  }

  Future<void> _loadPrices() async {
    final id = widget.insumoId;
    try {
      final dept = await AppCache.instance
          .cachedCall<List<Map<String, dynamic>>>(
        'insumo:$id:prices:dept:2000',
        () => insumos_api.getInsumoPricesByDepartment(id, limit: 2000),
      );
      final muni = await AppCache.instance
          .cachedCall<List<Map<String, dynamic>>>(
        'insumo:$id:prices:muni:2000',
        () => insumos_api.getInsumoPricesByMunicipality(id, limit: 2000),
      );
      if (!mounted) return;
      setState(() {
        _deptPrices = dept;
        _muniPrices = muni;
        _pricesLoaded = true;
        if (dept.isEmpty && muni.isNotEmpty) {
          _series = _PriceSeries.municipality;
        }
      });
    } catch (_) {
      if (mounted) setState(() => _pricesLoaded = true);
    }
  }

  Future<void> _loadAttribution(Map<String, dynamic> ins) async {
    try {
      final name = (ins['canonical_name'] ?? '').toString();
      if (name.isEmpty) return;
      final slug = slugify(name);
      final attr = await getImageAttribution('insumo', slug);
      if (!mounted) return;
      setState(() => _attribution = attr);
    } catch (_) {}
  }

  List<Map<String, dynamic>> get _activePrices =>
      _series == _PriceSeries.department ? _deptPrices : _muniPrices;

  List<_TimeRange> _timeRanges(Translations t) => [
        _TimeRange(t.time_1w, 7),
        _TimeRange(t.time_1m, 30),
        _TimeRange(t.time_3m, 90),
        _TimeRange(t.time_6m, 180),
        _TimeRange(t.time_1y, 365),
        _TimeRange(t.time_all, 0),
      ];

  List<int> _availableTimeRangeIndices(Translations t) {
    final src = _activePrices;
    if (src.isEmpty) return [];
    String newest = (src.first['price_date'] ?? '').toString();
    for (final p in src) {
      final d = (p['price_date'] ?? '').toString();
      if (d.compareTo(newest) > 0) newest = d;
    }
    if (newest.isEmpty) return [];
    final newestDate = DateTime.parse('${newest}T00:00:00');
    final daysOld = DateTime.now().difference(newestDate).inDays;
    final ranges = _timeRanges(t);
    final result = <int>[];
    for (var i = 0; i < ranges.length; i++) {
      final r = ranges[i];
      if (r.days == 0 || daysOld <= r.days) result.add(i);
    }
    return result;
  }

  List<Map<String, dynamic>> _timeFilteredPrices(Translations t) {
    final ranges = _timeRanges(t);
    final idx = _timeRangeIndex ?? 0;
    if (idx < 0 || idx >= ranges.length) return _activePrices;
    final tr = ranges[idx];
    if (tr.days == 0) return _activePrices;
    final since = DateTime.now().subtract(Duration(days: tr.days));
    final sinceStr = since.toIso8601String().split('T').first;
    return _activePrices
        .where((p) => (p['price_date'] ?? '').toString().compareTo(sinceStr) >= 0)
        .toList();
  }

  List<String> _chartPresentations(Translations t) {
    final s = <String>{};
    for (final p in _timeFilteredPrices(t)) {
      final pres = (p['presentation'] ?? '').toString();
      if (pres.isNotEmpty) s.add(pres);
    }
    final list = s.toList()..sort();
    return list;
  }

  List<Map<String, dynamic>> _presFilteredPrices(Translations t) {
    final base = _timeFilteredPrices(t);
    if (_chartPresentation == null) return base;
    return base.where((p) => p['presentation'] == _chartPresentation).toList();
  }

  bool get _muniHasCityData =>
      _series == _PriceSeries.municipality &&
      _muniPrices.any((p) => p['city_id'] != null);

  List<MapEntry<String, String>> _chartDepts(Translations t) {
    final m = <String, String>{};
    for (final p in _presFilteredPrices(t)) {
      if (_series == _PriceSeries.municipality && _muniHasCityData) {
        final key = p['city_id']?.toString();
        final name = (p['dim_city']?['canonical_name'] ?? '').toString();
        if (key != null && key.isNotEmpty && name.isNotEmpty) m[key] = name;
      } else {
        final key = (p['department_id'] ?? '').toString();
        final name = (p['dim_department']?['canonical_name'] ?? '').toString();
        if (key.isNotEmpty && name.isNotEmpty) m[key] = name;
      }
    }
    final entries = m.entries.toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    return entries;
  }

  List<_ChartPoint> _chartData(Translations t) {
    var rows = _presFilteredPrices(t);
    if (_chartDept != null) {
      rows = rows.where((p) {
        if (_series == _PriceSeries.municipality && _muniHasCityData) {
          return p['city_id']?.toString() == _chartDept;
        }
        return (p['department_id'] ?? '').toString() == _chartDept;
      }).toList();
    }
    final byDate = <String, List<double>>{};
    for (final p in rows) {
      final date = (p['price_date'] ?? '').toString();
      final price = (p['avg_price'] as num?)?.toDouble();
      if (date.isEmpty || price == null) continue;
      byDate.putIfAbsent(date, () => []).add(price);
    }
    final keys = byDate.keys.toList()..sort();
    return keys.map((d) {
      final list = byDate[d]!;
      final avg = list.reduce((a, b) => a + b) / list.length;
      return _ChartPoint(date: d, value: avg);
    }).toList();
  }

  // Latest price per department (for the dept tab list).
  List<Map<String, dynamic>> _latestPerDepartment() {
    final byDept = <String, Map<String, dynamic>>{};
    for (final p in _deptPrices) {
      final id = (p['department_id'] ?? '').toString();
      if (id.isEmpty) continue;
      final cur = byDept[id];
      final pd = (p['price_date'] ?? '').toString();
      if (cur == null || pd.compareTo((cur['price_date'] ?? '').toString()) > 0) {
        byDept[id] = p;
      }
    }
    final list = byDept.values.toList();
    list.sort((a, b) {
      final ap = (a['avg_price'] as num?)?.toDouble() ?? 0;
      final bp = (b['avg_price'] as num?)?.toDouble() ?? 0;
      return _sortAsc ? ap.compareTo(bp) : bp.compareTo(ap);
    });
    return list;
  }

  List<Map<String, dynamic>> _latestPerMunicipality() {
    var rows = _muniPrices;
    if (_muniListDeptFilter != null && _muniListDeptFilter!.isNotEmpty) {
      rows = rows
          .where((p) =>
              (p['department_id'] ?? '').toString() == _muniListDeptFilter)
          .toList();
    }
    final byKey = <String, Map<String, dynamic>>{};
    for (final p in rows) {
      final keyId = (p['city_id'] ?? p['department_id'] ?? '').toString();
      if (keyId.isEmpty) continue;
      final cur = byKey[keyId];
      final pd = (p['price_date'] ?? '').toString();
      if (cur == null ||
          pd.compareTo((cur['price_date'] ?? '').toString()) > 0) {
        byKey[keyId] = p;
      }
    }
    final list = byKey.values.toList();
    list.sort((a, b) {
      final ap = (a['avg_price'] as num?)?.toDouble() ?? 0;
      final bp = (b['avg_price'] as num?)?.toDouble() ?? 0;
      return _sortAsc ? ap.compareTo(bp) : bp.compareTo(ap);
    });
    return list;
  }

  List<MapEntry<String, String>> _muniDeptOptions() {
    final m = <String, String>{};
    for (final p in _muniPrices) {
      final id = (p['department_id'] ?? '').toString();
      final name = (p['dim_department']?['canonical_name'] ?? '').toString();
      if (id.isNotEmpty && name.isNotEmpty) m[id] = name;
    }
    final entries = m.entries.toList()
      ..sort((a, b) => a.value.compareTo(b.value));
    return entries;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.watch<SettingsProvider>().t;
    final watchlist = context.watch<WatchlistProvider>();

    if (_loading) {
      return const CupertinoPageScaffold(
        navigationBar: CupertinoNavigationBar(
          backgroundColor: AppColors.dark,
          middle: Text('Insumo',
              style: TextStyle(color: AppColors.textInverse)),
        ),
        child: Center(child: CupertinoActivityIndicator(radius: 14)),
      );
    }

    if (_notFound || _insumo == null) {
      return CupertinoPageScaffold(
        navigationBar: const CupertinoNavigationBar(
          backgroundColor: AppColors.dark,
          middle: Text('Insumo',
              style: TextStyle(color: AppColors.textInverse)),
        ),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Text(
              t.input_not_found,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: AppColors.textTertiary, fontSize: AppFontSize.md),
            ),
          ),
        ),
      );
    }

    final ins = _insumo!;
    final id = widget.insumoId;
    final name = (ins['canonical_name'] ?? '').toString();
    final isWatched = watchlist.isWatched(id);

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text(
          name,
          style: const TextStyle(color: AppColors.textInverse),
          overflow: TextOverflow.ellipsis,
        ),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          minSize: 0,
          onPressed: () =>
              watchlist.toggle(id, WatchlistItemType.insumo, name),
          child: Icon(
            isWatched ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
            color:
                isWatched ? const Color(0xFFFF3B30) : AppColors.textInverse,
            size: 22,
          ),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.only(bottom: 40),
          children: [
            _buildHero(ins),
            _buildHeader(ins),
            _buildStats(t),
            _buildPriceTabs(t),
            const SizedBox(height: AppSpacing.md),
            _buildPriceList(t),
            const SizedBox(height: AppSpacing.md),
            _buildChartCard(t),
            const SizedBox(height: AppSpacing.md),
            if (_attribution != null) _buildAttribution(),
            _buildComments(id),
          ],
        ),
      ),
    );
  }

  // ── Hero ───────────────────────────────────────────────────────────────
  Widget _buildHero(Map<String, dynamic> ins) {
    final url = getInsumoImageUrl(
      insumoName: (ins['canonical_name'] ?? '').toString(),
      subgrupo: (ins['subgrupo'] ?? '').toString(),
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.lg),
        child: SizedBox(
          height: 180,
          width: double.infinity,
          child: CachedNetworkImage(
            imageUrl: url,
            fit: BoxFit.cover,
            placeholder: (_, __) => Container(
              color: AppColors.borderLight,
              child: const Center(child: CupertinoActivityIndicator()),
            ),
            errorWidget: (_, __, ___) => Image.network(
              getInsumoFallbackUrl(),
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                color: AppColors.borderLight,
                child: const Icon(CupertinoIcons.lab_flask,
                    size: 48, color: AppColors.secondary),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ── Header ─────────────────────────────────────────────────────────────
  Widget _buildHeader(Map<String, dynamic> ins) {
    final grupo = (ins['grupo'] ?? '').toString();
    final subgrupo = (ins['subgrupo'] ?? '').toString();
    final name = (ins['canonical_name'] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (grupo.isNotEmpty)
            Text(
              grupo.toUpperCase(),
              style: const TextStyle(
                fontSize: AppFontSize.xs,
                color: AppColors.textTertiary,
                letterSpacing: 0.5,
              ),
            ),
          Text(
            name,
            style: const TextStyle(
              fontSize: AppFontSize.xl,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          if (subgrupo.isNotEmpty)
            Text(
              subgrupo,
              style: const TextStyle(
                fontSize: AppFontSize.sm,
                color: AppColors.textSecondary,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildStats(Translations t) {
    final deptCount =
        _deptPrices.map((p) => p['department_id']).toSet().length;
    final muniCount = _muniPrices
        .map((p) => p['city_id'] ?? p['department_id'])
        .toSet()
        .length;
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Row(
        children: [
          Expanded(
              child: _StatBox(value: '$deptCount', label: t.input_departments)),
          const SizedBox(width: AppSpacing.md),
          Expanded(
              child:
                  _StatBox(value: '$muniCount', label: t.input_municipalities)),
        ],
      ),
    );
  }

  Widget _buildPriceTabs(Translations t) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: SizedBox(
        width: double.infinity,
        child: CupertinoSlidingSegmentedControl<_PriceSeries>(
          groupValue: _series,
          onValueChanged: (v) {
            if (v == null) return;
            setState(() {
              _series = v;
              _chartDept = null;
              _chartPresentation = null;
            });
          },
          children: {
            _PriceSeries.department: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Text(t.input_departments),
            ),
            _PriceSeries.municipality: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Text(t.input_municipalities),
            ),
          },
        ),
      ),
    );
  }

  Widget _buildPriceList(Translations t) {
    if (!_pricesLoaded) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Center(child: CupertinoActivityIndicator()),
      );
    }

    final rows = _series == _PriceSeries.department
        ? _latestPerDepartment()
        : _latestPerMunicipality();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _series == _PriceSeries.department
                      ? t.input_price_by_dept
                      : t.input_municipalities,
                  style: const TextStyle(
                    fontSize: AppFontSize.md,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minSize: 0,
                onPressed: () => setState(() => _sortAsc = !_sortAsc),
                child: Row(
                  children: [
                    Icon(
                      _sortAsc
                          ? CupertinoIcons.arrow_up
                          : CupertinoIcons.arrow_down,
                      size: 14,
                      color: AppColors.textSecondary,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      _sortAsc ? 'Menor' : 'Mayor',
                      style: const TextStyle(
                          fontSize: AppFontSize.xs,
                          color: AppColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        if (_series == _PriceSeries.municipality &&
            _muniDeptOptions().isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
            child: _DeptDropdown(
              options: _muniDeptOptions(),
              selected: _muniListDeptFilter,
              onChanged: (v) => setState(() => _muniListDeptFilter = v),
            ),
          ),
        if (rows.isEmpty)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Center(
              child: Text(
                t.input_no_data,
                style: const TextStyle(
                    color: AppColors.textTertiary, fontSize: AppFontSize.sm),
              ),
            ),
          )
        else
          ...rows.map((row) => _PriceRow(
                row: row,
                isMunicipality: _series == _PriceSeries.municipality,
              )),
      ],
    );
  }

  Widget _buildChartCard(Translations t) {
    final ranges = _timeRanges(t);
    final available = _availableTimeRangeIndices(t);
    if (_timeRangeIndex == null || !available.contains(_timeRangeIndex)) {
      if (available.isNotEmpty) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) setState(() => _timeRangeIndex = available.first);
        });
      }
    }
    final data = _chartData(t);
    final presList = _chartPresentations(t);
    final deptList = _chartDepts(t);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: AppCard(
        child: ExpandableSection(
          title: t.input_price_history,
          icon: CupertinoIcons.chart_bar_alt_fill,
          initiallyExpanded: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (available.length > 1)
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: available.map((i) {
                    final r = ranges[i];
                    final active = i == _timeRangeIndex;
                    return _MiniChip(
                      label: r.label,
                      active: active,
                      color: AppColors.primaryDark,
                      onTap: () => setState(() => _timeRangeIndex = i),
                    );
                  }).toList(),
                ),
              if (presList.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: presList.map((p) {
                    final active =
                        _chartPresentation == p || presList.length == 1;
                    return _MiniChip(
                      label: p,
                      active: active,
                      color: AppColors.primaryDark,
                      onTap: () => setState(() => _chartPresentation = p),
                    );
                  }).toList(),
                ),
              ],
              if (deptList.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.xs,
                  runSpacing: AppSpacing.xs,
                  children: [
                    if (deptList.length > 1)
                      _MiniChip(
                        label: 'Nacional',
                        active: _chartDept == null,
                        color: AppColors.accentBlue,
                        onTap: () => setState(() => _chartDept = null),
                      ),
                    ...deptList.map((e) {
                      final active =
                          _chartDept == e.key || deptList.length == 1;
                      return _MiniChip(
                        label: e.value,
                        active: active,
                        color: AppColors.accentBlue,
                        onTap: () => setState(() => _chartDept =
                            _chartDept == e.key ? null : e.key),
                      );
                    }),
                  ],
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              if (data.length > 1)
                SizedBox(
                  height: 180,
                  child: _PriceLineChart(points: data),
                )
              else
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.xl),
                  child: Center(
                    child: Text(
                      t.input_no_data,
                      style: const TextStyle(
                          color: AppColors.textTertiary,
                          fontSize: AppFontSize.sm),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAttribution() {
    final attr = _attribution;
    if (attr == null) return const SizedBox.shrink();
    final author = attr.author ?? '';
    final source = attr.sourceName;
    final license = attr.license ?? '';
    if (author.isEmpty && source.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Text(
        [
          if (author.isNotEmpty) 'Foto: $author',
          if (source.isNotEmpty) source,
          if (license.isNotEmpty) license,
        ].join(' · '),
        style: const TextStyle(
          fontSize: AppFontSize.xs,
          color: AppColors.textTertiary,
        ),
      ),
    );
  }

  Widget _buildComments(String id) {
    final settings = context.watch<SettingsProvider>().settings;
    if (!settings.commentsEnabled) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
      child: AppCard(
        child: CommentsSection(entityType: 'insumo', entityId: id),
      ),
    );
  }
}

// ─── Sub-widgets ────────────────────────────────────────────────────────

class _ChartPoint {
  final String date;
  final double value;
  const _ChartPoint({required this.date, required this.value});
}

class _PriceLineChart extends StatelessWidget {
  final List<_ChartPoint> points;
  const _PriceLineChart({required this.points});

  @override
  Widget build(BuildContext context) {
    if (points.length < 2) return const SizedBox.shrink();
    final spots = <FlSpot>[];
    for (var i = 0; i < points.length; i++) {
      spots.add(FlSpot(i.toDouble(), points[i].value));
    }
    final values = points.map((p) => p.value).toList();
    final minY = values.reduce((a, b) => a < b ? a : b);
    final maxY = values.reduce((a, b) => a > b ? a : b);
    final pad = (maxY - minY) * 0.1;
    return LineChart(
      LineChartData(
        minX: 0,
        maxX: (points.length - 1).toDouble(),
        minY: (minY - pad).clamp(0, double.infinity),
        maxY: maxY + pad,
        gridData: const FlGridData(show: false),
        titlesData: FlTitlesData(
          show: true,
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 48,
              getTitlesWidget: (value, _) => Text(
                formatCOPCompact(value),
                style: const TextStyle(
                    fontSize: 10, color: AppColors.textTertiary),
              ),
            ),
          ),
          bottomTitles: const AxisTitles(),
          topTitles: const AxisTitles(),
          rightTitles: const AxisTitles(),
        ),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: AppColors.secondary,
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: AppColors.secondary.withValues(alpha: 0.1),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatBox extends StatelessWidget {
  final String value;
  final String label;
  const _StatBox({required this.value, required this.label});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: AppFontSize.xl,
                  fontWeight: FontWeight.w700,
                  color: AppColors.secondary)),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(
                  fontSize: AppFontSize.xs, color: AppColors.textSecondary)),
        ],
      ),
    );
  }
}

class _PriceRow extends StatelessWidget {
  final Map<String, dynamic> row;
  final bool isMunicipality;
  const _PriceRow({required this.row, required this.isMunicipality});

  @override
  Widget build(BuildContext context) {
    final deptName =
        (row['dim_department']?['canonical_name'] ?? '').toString();
    final cityName = (row['dim_city']?['canonical_name'] ?? '').toString();
    final priceText = formatCOP(row['avg_price'] as num?);
    final pres = (row['presentation'] ?? '').toString();
    final dateStr = (row['price_date'] ?? '').toString();
    final dateFormatted = dateStr.isNotEmpty ? formatDateShort(dateStr) : '';
    final primary = isMunicipality && cityName.isNotEmpty ? cityName : deptName;
    final secondary = isMunicipality && cityName.isNotEmpty ? deptName : '';

    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.sm),
      child: AppCard(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(primary,
                      style: const TextStyle(
                          fontSize: AppFontSize.sm,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textPrimary)),
                  if (secondary.isNotEmpty)
                    Text(secondary,
                        style: const TextStyle(
                            fontSize: AppFontSize.xs,
                            color: AppColors.textSecondary)),
                  if (pres.isNotEmpty)
                    Text(pres,
                        style: const TextStyle(
                            fontSize: AppFontSize.xs,
                            color: AppColors.textTertiary)),
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
                      color: AppColors.secondary,
                      fontFamily: 'Menlo',
                    )),
                if (dateFormatted.isNotEmpty)
                  Text(dateFormatted,
                      style: const TextStyle(
                          fontSize: AppFontSize.xs,
                          color: AppColors.textTertiary)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MiniChip extends StatelessWidget {
  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;
  const _MiniChip({
    required this.label,
    required this.active,
    required this.color,
    required this.onTap,
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
          color: active ? color : AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.full),
          border: Border.all(
            color: active ? color : AppColors.borderLight,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppFontSize.xs,
            fontWeight: FontWeight.w500,
            color: active ? AppColors.textInverse : AppColors.textSecondary,
          ),
        ),
      ),
    );
  }
}

class _DeptDropdown extends StatelessWidget {
  final List<MapEntry<String, String>> options;
  final String? selected;
  final ValueChanged<String?> onChanged;
  const _DeptDropdown({
    required this.options,
    required this.selected,
    required this.onChanged,
  });

  String _label() {
    if (selected == null) return 'Todos los departamentos';
    final found = options.firstWhere(
      (e) => e.key == selected,
      orElse: () => const MapEntry('', ''),
    );
    return found.value.isEmpty ? 'Todos los departamentos' : found.value;
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _showPicker(context),
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
            Expanded(
              child: Text(
                _label(),
                style: const TextStyle(
                    fontSize: AppFontSize.sm, color: AppColors.textPrimary),
              ),
            ),
            const Icon(CupertinoIcons.chevron_down,
                size: 14, color: AppColors.textTertiary),
          ],
        ),
      ),
    );
  }

  void _showPicker(BuildContext context) {
    final all = [const MapEntry<String, String>('', 'Todos'), ...options];
    var initial = all.indexWhere((e) => e.key == (selected ?? ''));
    if (initial < 0) initial = 0;
    showCupertinoModalPopup<void>(
      context: context,
      builder: (ctx) => Container(
        height: 260,
        color: AppColors.surface,
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                CupertinoButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Listo'),
                ),
              ],
            ),
            Expanded(
              child: CupertinoPicker(
                itemExtent: 32,
                scrollController:
                    FixedExtentScrollController(initialItem: initial),
                onSelectedItemChanged: (i) {
                  final entry = all[i];
                  onChanged(entry.key.isEmpty ? null : entry.key);
                },
                children: all
                    .map((e) => Center(
                        child: Text(e.value.isEmpty ? 'Todos' : e.value,
                            maxLines: 1, overflow: TextOverflow.ellipsis)))
                    .toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
