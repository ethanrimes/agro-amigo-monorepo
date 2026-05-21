import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import 'package:agroamigo_iphone/theme/theme.dart';
import 'package:agroamigo_iphone/state/settings_provider.dart';
import 'package:agroamigo_iphone/api/markets_api.dart';
import 'package:agroamigo_iphone/services/format.dart';

const _kNationalAvg = '__national__';

/// Port of `MarketSupplyComparator.tsx`.
///
/// Search-and-pick market supply comparator. Shows a kg diff table grouped by
/// category/subcategory with overall average at the bottom.
class MarketSupplyComparator extends StatefulWidget {
  const MarketSupplyComparator({
    super.key,
    required this.currentMarket,
    required this.supply,
    required this.products,
    required this.markets,
  });

  final Map<String, dynamic> currentMarket;
  final List<Map<String, dynamic>> supply;
  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> markets;

  @override
  State<MarketSupplyComparator> createState() =>
      _MarketSupplyComparatorState();
}

class _MarketSupplyComparatorState extends State<MarketSupplyComparator> {
  String? _compId;
  List<Map<String, dynamic>> _compData = [];
  bool _loading = false;

  // Aggregated kg per product_id for the current market.
  Map<String, double> get _supplyA {
    final map = <String, double>{};
    for (final s in widget.supply) {
      final pid = s['product_id'] as String;
      map[pid] = (map[pid] ?? 0) + ((s['quantity_kg'] as num?)?.toDouble() ?? 0);
    }
    return map;
  }

  // Product metadata lookup.
  Map<String, _ProductInfo> get _productInfo {
    final map = <String, _ProductInfo>{};
    for (final p in widget.products) {
      map[p['product_id'] as String] = _ProductInfo(
        name: (p['dim_product'] as Map?)?['canonical_name'] as String? ??
            'Producto',
        category: ((p['dim_product'] as Map?)?['dim_subcategory']
                    as Map?)?['dim_category']?['canonical_name'] as String? ??
            'Otro',
        subcategory:
            ((p['dim_product'] as Map?)?['dim_subcategory'] as Map?)?[
                    'canonical_name'] as String? ??
                'General',
      );
    }
    for (final s in widget.supply) {
      final pid = s['product_id'] as String;
      if (!map.containsKey(pid)) {
        map[pid] = _ProductInfo(
          name: (s['dim_product'] as Map?)?['canonical_name'] as String? ??
              'Producto',
          category: 'Otro',
          subcategory: 'General',
        );
      }
    }
    return map;
  }

  @override
  void didUpdateWidget(MarketSupplyComparator old) {
    super.didUpdateWidget(old);
    if (old.supply != widget.supply && _compId != null) {
      _fetchComp();
    }
  }

  Future<void> _fetchComp() async {
    if (_compId == null) {
      setState(() => _compData = []);
      return;
    }
    setState(() => _loading = true);
    try {
      final pids = _supplyA.keys.toList();
      List<Map<String, dynamic>> data;
      if (_compId == _kNationalAvg) {
        data = await getNationalSupplyAverages(pids, days: 30);
      } else {
        final raw = await getMarketSupply(_compId!, days: 30);
        // Aggregate kg per product_id.
        final agg = <String, double>{};
        for (final s in raw) {
          final pid = s['product_id'] as String;
          agg[pid] =
              (agg[pid] ?? 0) + ((s['quantity_kg'] as num?)?.toDouble() ?? 0);
        }
        data = agg.entries
            .map((e) => {'product_id': e.key, 'quantity_kg': e.value})
            .toList();
      }
      if (mounted) setState(() => _compData = data);
    } catch (_) {
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _selectMarket(String id) {
    setState(() => _compId = id);
    _fetchComp();
  }

  void _openPicker(BuildContext context, dynamic t) {
    showCupertinoModalPopup<void>(
      context: context,
      builder: (_) => _SupplyPickerSheet(
        t: t,
        markets: widget.markets,
        excludeId: widget.currentMarket['id'] as String?,
        onSelect: _selectMarket,
      ),
    );
  }

  void _clearComp() => setState(() {
        _compId = null;
        _compData = [];
      });

  _SupplyComparison? _buildComparison() {
    if (_compId == null || _compData.isEmpty) return null;

    final bMap = <String, double>{};
    for (final s in _compData) {
      bMap[s['product_id'] as String] =
          (s['quantity_kg'] as num?)?.toDouble() ?? 0;
    }

    final supplyA = _supplyA;
    final pInfo = _productInfo;
    final rows = <_SupplyRow>[];

    for (final entry in supplyA.entries) {
      final pid = entry.key;
      final kgA = entry.value;
      final kgB = bMap[pid];
      if (kgB == null) continue;
      final info = pInfo[pid];
      final pctDiff = kgA > 0 ? ((kgB - kgA) / kgA) * 100 : null;
      rows.add(_SupplyRow(
        productId: pid,
        name: info?.name ?? 'Producto',
        category: info?.category ?? 'Otro',
        subcategory: info?.subcategory ?? 'General',
        kgA: kgA,
        kgB: kgB,
        pctDiff: pctDiff,
      ));
    }

    final catMap = <String, Map<String, List<_SupplyRow>>>{};
    for (final r in rows) {
      catMap.putIfAbsent(r.category, () => {});
      catMap[r.category]!.putIfAbsent(r.subcategory, () => []);
      catMap[r.category]![r.subcategory]!.add(r);
    }

    final groups = catMap.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));

    final groupList = groups.map((catEntry) {
      final subs = catEntry.value.entries.toList()
        ..sort((a, b) => a.key.compareTo(b.key));
      final subList = subs.map((subEntry) {
        final items = subEntry.value
          ..sort((a, b) => a.name.compareTo(b.name));
        final matched = items.where((r) => r.pctDiff != null).toList();
        final avgDiff = matched.isNotEmpty
            ? matched.map((r) => r.pctDiff!).reduce((a, b) => a + b) /
                matched.length
            : null;
        return _SupplySubGroup(
          name: subEntry.key,
          items: items,
          avgDiff: avgDiff,
          matchCount: matched.length,
        );
      }).toList();
      return _SupplyCatGroup(category: catEntry.key, subcategories: subList);
    }).toList();

    final matched = rows.where((r) => r.pctDiff != null).toList();
    final overallAvg = matched.isNotEmpty
        ? matched.map((r) => r.pctDiff!).reduce((a, b) => a + b) /
            matched.length
        : null;

    return _SupplyComparison(
      groups: groupList,
      overallAvg: overallAvg,
      matchCount: matched.length,
      totalA: supplyA.length,
    );
  }

  Color _diffColor(double? pct) {
    if (pct == null) return AppColors.textTertiary;
    if (pct > 2) return AppColors.priceUp;
    if (pct < -2) return AppColors.priceDown;
    return AppColors.textTertiary;
  }

  String _fmtDiff(double? pct) {
    if (pct == null) return '—';
    return '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(1)}%';
  }

  String get _compName {
    if (_compId == _kNationalAvg) {
      return context.read<SettingsProvider>().t.compare_national_avg;
    }
    return widget.markets
            .firstWhere((m) => m['id'] == _compId,
                orElse: () => const {})['canonical_name'] as String? ??
        '';
  }

  @override
  Widget build(BuildContext context) {
    if (widget.supply.isEmpty) return const SizedBox.shrink();
    final t = context.watch<SettingsProvider>().t;
    final comparison = _buildComparison();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header.
        Row(
          children: [
            const Icon(CupertinoIcons.arrow_right_arrow_left,
                size: 16, color: AppColors.accentBlue),
            const SizedBox(width: AppSpacing.sm),
            Text(t.compare_supply_title,
                style: const TextStyle(
                    fontSize: AppFontSize.md,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary)),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),

        // Market selector.
        GestureDetector(
          onTap: () => _openPicker(context, t),
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            decoration: BoxDecoration(
              color: AppColors.background,
              borderRadius: BorderRadius.circular(AppRadius.md),
              border: Border.all(color: AppColors.borderLight),
            ),
            child: Row(
              children: [
                const Icon(CupertinoIcons.search,
                    size: 14, color: AppColors.textTertiary),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    _compId != null ? _compName : t.compare_select_market,
                    style: TextStyle(
                        fontSize: AppFontSize.sm,
                        color: _compId != null
                            ? AppColors.textPrimary
                            : AppColors.textTertiary),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (_compId != null)
                  GestureDetector(
                    onTap: _clearComp,
                    child: const Icon(CupertinoIcons.clear_circled,
                        size: 16, color: AppColors.textTertiary),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.md),

        // Loading.
        if (_loading)
          const Padding(
            padding: EdgeInsets.all(AppSpacing.lg),
            child: CupertinoActivityIndicator(),
          ),

        // Results table.
        if (!_loading &&
            _compId != null &&
            comparison != null &&
            comparison.matchCount > 0)
          _buildTable(context, t, comparison),

        // No match.
        if (!_loading &&
            _compId != null &&
            (comparison == null || comparison.matchCount == 0))
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Center(
              child: Text(t.compare_no_match,
                  style: const TextStyle(
                      fontSize: AppFontSize.sm,
                      color: AppColors.textTertiary)),
            ),
          ),
      ],
    );
  }

  Widget _buildTable(BuildContext context, dynamic t, _SupplyComparison comp) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${comp.matchCount} / ${comp.totalA} ${t.compare_matching}',
            style: const TextStyle(
                fontSize: AppFontSize.xs, color: AppColors.textTertiary)),
        const SizedBox(height: AppSpacing.xs),
        Row(
          children: [
            const Expanded(
              child: Text('',
                  style: TextStyle(fontSize: AppFontSize.xs)),
            ),
            _colH(widget.currentMarket['canonical_name'] as String? ?? '', 68),
            _colH(_compName, 68),
            _colH(t.compare_diff as String, 52),
          ],
        ),
        for (final group in comp.groups) ...[
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
            child: Text(group.category.toUpperCase(),
                style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    fontWeight: FontWeight.w700,
                    color: AppColors.accentBlue,
                    letterSpacing: 0.5)),
          ),
          const Divider(height: 1, color: AppColors.borderLight),
          for (final sub in group.subcategories) ...[
            if (group.subcategories.length > 1)
              Padding(
                padding:
                    const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                child: Text(sub.name,
                    style: const TextStyle(
                        fontSize: AppFontSize.xs,
                        fontWeight: FontWeight.w600,
                        color: AppColors.textSecondary)),
              ),
            for (final row in sub.items)
              Container(
                padding: const EdgeInsets.symmetric(
                    vertical: 3, horizontal: AppSpacing.xs),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                        color: AppColors.borderLight.withOpacity(0.3),
                        width: 0.5),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(row.name,
                          style: const TextStyle(
                              fontSize: AppFontSize.sm,
                              color: AppColors.textPrimary)),
                    ),
                    _kgCell(formatKg(row.kgA)),
                    _kgCell(formatKg(row.kgB)),
                    _diffCell(_fmtDiff(row.pctDiff),
                        _diffColor(row.pctDiff)),
                  ],
                ),
              ),
            if (sub.avgDiff != null && sub.matchCount > 1)
              Container(
                color: AppColors.background,
                padding: const EdgeInsets.symmetric(
                    vertical: 3, horizontal: AppSpacing.xs),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(sub.name,
                          style: const TextStyle(
                              fontSize: AppFontSize.xs,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textSecondary,
                              fontStyle: FontStyle.italic)),
                    ),
                    const SizedBox(width: 68),
                    const SizedBox(width: 68),
                    _diffCell(
                      _fmtDiff(sub.avgDiff),
                      _diffColor(sub.avgDiff),
                      bold: true,
                    ),
                  ],
                ),
              ),
          ],
        ],
        if (comp.overallAvg != null)
          Container(
            padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.sm, horizontal: AppSpacing.xs),
            decoration: const BoxDecoration(
              border: Border(
                  top: BorderSide(color: AppColors.accentBlue, width: 2)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(t.compare_overall_avg as String,
                      style: const TextStyle(
                          fontSize: AppFontSize.sm,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary)),
                ),
                const SizedBox(width: 68),
                const SizedBox(width: 68),
                _diffCell(
                  _fmtDiff(comp.overallAvg),
                  _diffColor(comp.overallAvg),
                  fontSize: AppFontSize.sm,
                  bold: true,
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _colH(String label, double width) => SizedBox(
        width: width,
        child: Text(label,
            textAlign: TextAlign.right,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                fontSize: AppFontSize.xs,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary)),
      );

  Widget _kgCell(String text) => SizedBox(
        width: 68,
        child: Text(text,
            textAlign: TextAlign.right,
            style: const TextStyle(
                fontSize: AppFontSize.sm,
                fontFamily: 'Courier',
                color: AppColors.textPrimary)),
      );

  Widget _diffCell(String text, Color color,
          {bool bold = false, double fontSize = AppFontSize.xs}) =>
      SizedBox(
        width: 52,
        child: Text(text,
            textAlign: TextAlign.right,
            style: TextStyle(
                fontSize: fontSize,
                fontWeight: bold ? FontWeight.w700 : FontWeight.w600,
                fontFamily: 'Courier',
                color: color)),
      );
}

// ── Data models ──────────────────────────────────────────────────────────────

class _ProductInfo {
  const _ProductInfo(
      {required this.name,
      required this.category,
      required this.subcategory});
  final String name;
  final String category;
  final String subcategory;
}

class _SupplyRow {
  const _SupplyRow({
    required this.productId,
    required this.name,
    required this.category,
    required this.subcategory,
    required this.kgA,
    required this.kgB,
    this.pctDiff,
  });
  final String productId;
  final String name;
  final String category;
  final String subcategory;
  final double kgA;
  final double kgB;
  final double? pctDiff;
}

class _SupplySubGroup {
  const _SupplySubGroup({
    required this.name,
    required this.items,
    required this.avgDiff,
    required this.matchCount,
  });
  final String name;
  final List<_SupplyRow> items;
  final double? avgDiff;
  final int matchCount;
}

class _SupplyCatGroup {
  const _SupplyCatGroup(
      {required this.category, required this.subcategories});
  final String category;
  final List<_SupplySubGroup> subcategories;
}

class _SupplyComparison {
  const _SupplyComparison({
    required this.groups,
    required this.overallAvg,
    required this.matchCount,
    required this.totalA,
  });
  final List<_SupplyCatGroup> groups;
  final double? overallAvg;
  final int matchCount;
  final int totalA;
}

// ── Reusable picker row ──────────────────────────────────────────────────────

class _PickerItem extends StatelessWidget {
  const _PickerItem({
    required this.name,
    required this.sub,
    required this.onTap,
    this.nameColor,
  });
  final String name;
  final String sub;
  final VoidCallback onTap;
  final Color? nameColor;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
        decoration: const BoxDecoration(
          border: Border(
            bottom: BorderSide(color: AppColors.borderLight, width: 0.5),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(name,
                style: TextStyle(
                    fontSize: AppFontSize.sm,
                    fontWeight: nameColor != null ? FontWeight.w600 : null,
                    color: nameColor ?? AppColors.textPrimary)),
            if (sub.isNotEmpty)
              Text(sub,
                  style: const TextStyle(
                      fontSize: AppFontSize.xs,
                      color: AppColors.textTertiary)),
          ],
        ),
      ),
    );
  }
}

class _SupplyPickerSheet extends StatefulWidget {
  const _SupplyPickerSheet({
    required this.t,
    required this.markets,
    required this.excludeId,
    required this.onSelect,
  });
  final dynamic t;
  final List<Map<String, dynamic>> markets;
  final String? excludeId;
  final void Function(String id) onSelect;

  @override
  State<_SupplyPickerSheet> createState() => _SupplyPickerSheetState();
}

class _SupplyPickerSheetState extends State<_SupplyPickerSheet> {
  String _search = '';

  List<Map<String, dynamic>> get _filtered {
    final q = _search.toLowerCase();
    return widget.markets
        .where((m) => m['id'] != widget.excludeId)
        .where((m) =>
            q.isEmpty ||
            (m['canonical_name'] as String? ?? '').toLowerCase().contains(q) ||
            ((m['dim_city'] as Map?)?['canonical_name'] as String? ?? '')
                .toLowerCase()
                .contains(q))
        .toList();
  }

  void _pick(String id) {
    Navigator.of(context).pop();
    widget.onSelect(id);
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.t;
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.7,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.lg)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg, vertical: AppSpacing.md),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(t.compare_search_market as String,
                    style: const TextStyle(
                        fontSize: AppFontSize.lg,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary)),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Icon(CupertinoIcons.xmark,
                      color: AppColors.textPrimary),
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: AppColors.borderLight),
          Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
            child: Row(
              children: [
                const Icon(CupertinoIcons.search,
                    size: 16, color: AppColors.textTertiary),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: CupertinoTextField(
                    autofocus: true,
                    placeholder: t.compare_search_market as String,
                    placeholderStyle: const TextStyle(
                        color: AppColors.textTertiary,
                        fontSize: AppFontSize.md),
                    style: const TextStyle(
                        color: AppColors.textPrimary, fontSize: AppFontSize.md),
                    decoration: const BoxDecoration(),
                    onChanged: (v) => setState(() => _search = v),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: AppColors.borderLight),
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                _PickerItem(
                  name: t.compare_national_avg as String,
                  sub: t.compare_all_markets as String,
                  nameColor: AppColors.primary,
                  onTap: () => _pick(_kNationalAvg),
                ),
                ..._filtered.map((m) {
                  final city =
                      (m['dim_city'] as Map?)?['canonical_name'] as String? ??
                          '';
                  final dept = ((m['dim_city'] as Map?)?['dim_department']
                      as Map?)?['canonical_name'] as String?;
                  final sub = dept != null ? '$city, $dept' : city;
                  return _PickerItem(
                    name: m['canonical_name'] as String? ?? '',
                    sub: sub,
                    onTap: () => _pick(m['id'] as String),
                  );
                }),
                if (_filtered.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Center(
                      child: Text(t.compare_no_results as String,
                          style: const TextStyle(
                              fontSize: AppFontSize.sm,
                              color: AppColors.textTertiary)),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
