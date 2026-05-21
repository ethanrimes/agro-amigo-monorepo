import 'dart:async';
import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../api/map_api.dart';
import '../api/products_api.dart';
import '../services/cache.dart';
import '../services/format.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../translations/translations.dart';
import 'market_detail_screen.dart';

/// Port of `agroamigo-app/app/(tabs)/map.tsx` — Colombia choropleth + market
/// markers with a product/presentation/mode picker.
class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

enum _Mode { price, supply }

const LatLng _kColombiaCenter = LatLng(4.5, -73.0);
const double _kColombiaZoom = 5.0;

const List<Color> _kPriceColors = [
  Color(0xFF2D7D46),
  Color(0xFF4CAF50),
  Color(0xFF8BC34A),
  Color(0xFFCDDC39),
  Color(0xFFFFC107),
  Color(0xFFFF9800),
  Color(0xFFF44336),
];

const List<Color> _kSupplyColors = [
  Color(0xFFE3F2FD),
  Color(0xFF90CAF9),
  Color(0xFF42A5F5),
  Color(0xFF1E88E5),
  Color(0xFF1565C0),
  Color(0xFF0D47A1),
  Color(0xFF1A237E),
];

const Color _kNoDataColor = Color(0xFFE0E0E0);

/// Linear-segment lookup over a 7-color scale — bucket index `floor(t*6)`,
/// returns `colorScale[idx + 1]` so values cluster on the warm/cool end of
/// the palette. Verbatim port of the React Native `interpolateColor`.
Color interpolateColor(double value, double min, double max, List<Color> colorScale) {
  if (max == min) return colorScale[3];
  final t = ((value - min) / (max - min)).clamp(0.0, 1.0);
  var idx = (t * (colorScale.length - 1)).floor();
  if (idx > colorScale.length - 2) idx = colorScale.length - 2;
  return colorScale[idx + 1];
}

/// One ring of a department polygon, ready to drop into a flutter_map
/// `Polygon`. Carries the divipola code + display name so we can colour it
/// and respond to taps.
class _DeptPolygon {
  final String divipola;
  final String name;
  final List<LatLng> ring;
  _DeptPolygon(this.divipola, this.name, this.ring);
}

class _MapScreenState extends State<MapScreen> {
  // Map state.
  bool _loading = true;
  _Mode _mode = _Mode.price;
  final MapController _mapController = MapController();

  // Loaded layers.
  List<_DeptPolygon> _polygons = const [];
  List<Map<String, dynamic>> _departments = const [];
  List<Map<String, dynamic>> _allMarkets = const [];

  // Active dataset.
  List<Map<String, dynamic>> _priceData = const [];
  List<Map<String, dynamic>> _supplyData = const [];

  // Product picker.
  Map<String, dynamic>? _selectedProduct;
  bool _showProductPicker = false;
  String _productSearch = '';
  List<Map<String, dynamic>> _productResults = const [];
  bool _searchLoading = false;
  Timer? _searchDebounce;
  final TextEditingController _searchController = TextEditingController();

  // Active market filtering — null means show every market (no product).
  Set<String>? _activeMarketIds;

  // Presentation selector (price mode only).
  List<Map<String, dynamic>> _presentations = const [];
  Map<String, dynamic>? _selectedPresentation;

  @override
  void initState() {
    super.initState();
    _loadStaticLayers();
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    _mapController.dispose();
    super.dispose();
  }

  Future<void> _loadStaticLayers() async {
    try {
      final results = await Future.wait([
        AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
          'map:departments',
          () => MapApi.getDepartments(),
        ),
        AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
          'map:marketLocations',
          () => MapApi.getMarketLocations(),
        ),
        _loadGeoJsonPolygons(),
      ]);
      if (!mounted) return;
      setState(() {
        _departments = results[0] as List<Map<String, dynamic>>;
        _allMarkets = (results[1] as List<Map<String, dynamic>>)
            .where((m) => m['lat'] != null && m['lng'] != null)
            .toList();
        _polygons = results[2] as List<_DeptPolygon>;
      });
      await _loadMapData();
    } catch (e) {
      // Surface the error by clearing the loading state — the empty map and
      // the "pick a product" prompt give the user a path forward.
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<List<_DeptPolygon>> _loadGeoJsonPolygons() async {
    final raw = await rootBundle.loadString('assets/colombia-departments.json');
    final geo = jsonDecode(raw) as Map<String, dynamic>;
    final features = (geo['features'] as List?) ?? const [];
    final polygons = <_DeptPolygon>[];
    for (final f in features) {
      final feature = f as Map<String, dynamic>;
      final props = (feature['properties'] as Map?) ?? const {};
      final divipola = props['DPTO']?.toString() ?? '';
      final name = props['NOMBRE_DPT']?.toString() ?? '';
      final geom = feature['geometry'] as Map<String, dynamic>?;
      if (geom == null) continue;
      final type = geom['type'];
      final coords = geom['coordinates'] as List?;
      if (coords == null) continue;
      if (type == 'Polygon') {
        for (final ring in coords) {
          polygons.add(_DeptPolygon(divipola, name, _ringToLatLngs(ring as List)));
        }
      } else if (type == 'MultiPolygon') {
        for (final poly in coords) {
          for (final ring in (poly as List)) {
            polygons.add(_DeptPolygon(divipola, name, _ringToLatLngs(ring as List)));
          }
        }
      }
    }
    return polygons;
  }

  List<LatLng> _ringToLatLngs(List ring) {
    return ring
        .map((p) {
          final pt = p as List;
          // GeoJSON: [lng, lat].
          return LatLng((pt[1] as num).toDouble(), (pt[0] as num).toDouble());
        })
        .toList(growable: false);
  }

  Future<void> _loadMapData() async {
    final pid = _selectedProduct?['id'] as String?;
    final presId = _selectedPresentation?['presentation_id'] as String?;
    final uId = _selectedPresentation?['units_id'] as String?;

    // No product → skip cross-product aggregates (averaging papa+aguacate
    // has no meaning, summing every product's kg also blows up the query).
    if (pid == null) {
      if (!mounted) return;
      setState(() {
        _priceData = const [];
        _supplyData = const [];
        _activeMarketIds = null;
        _loading = false;
      });
      return;
    }

    // Product picked but presentation still resolving in price mode — hold
    // the existing map until the presentation lands instead of thrashing.
    if (_mode == _Mode.price && presId == null) return;

    if (mounted) setState(() => _loading = true);
    try {
      final keySuffix =
          '$pid:${_mode == _Mode.price ? 'price' : 'supply'}:30:${presId ?? ''}:${uId ?? ''}';

      final priceFuture = _mode == _Mode.price
          ? AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
              'map:prices:$keySuffix',
              () => MapApi.getPricesByDepartment(pid, 30, presId, uId),
            )
          : Future.value(<Map<String, dynamic>>[]);

      final supplyFuture = _mode == _Mode.supply
          ? AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
              'map:supply:$keySuffix',
              () => MapApi.getSupplyByDepartment(pid, 30),
            )
          : Future.value(<Map<String, dynamic>>[]);

      final results = await Future.wait([priceFuture, supplyFuture]);
      final ids = await AppCache.instance.cachedCall<List<String>>(
        'map:activeMarkets:$keySuffix',
        () => MapApi.getMarketsWithProductData(
            pid, _mode == _Mode.price ? 'price' : 'supply', 30, presId, uId),
      );

      if (!mounted) return;
      setState(() {
        _priceData = results[0];
        _supplyData = results[1];
        _activeMarketIds = ids.toSet();
      });
    } catch (_) {
      // Swallow — leave previous data on screen rather than wipe it.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadPresentations() async {
    final pid = _selectedProduct?['id'] as String?;
    if (pid == null || _mode != _Mode.price) {
      setState(() {
        _presentations = const [];
        _selectedPresentation = null;
      });
      return;
    }
    try {
      final list = await AppCache.instance.cachedCall<List<Map<String, dynamic>>>(
        'map:presentations:$pid:30',
        () => MapApi.getProductPresentationsForMap(pid, 30),
      );
      if (!mounted) return;
      setState(() {
        _presentations = list;
        _selectedPresentation = list.isNotEmpty ? list.first : null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _presentations = const [];
        _selectedPresentation = null;
      });
    }
  }

  void _onSearchChanged(String value) {
    setState(() => _productSearch = value);
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () async {
      if (value.length < 2) {
        if (mounted) setState(() => _productResults = const []);
        return;
      }
      if (mounted) setState(() => _searchLoading = true);
      try {
        final data = await ProductsApi.getProducts(search: value, limit: 20);
        if (!mounted) return;
        setState(() => _productResults = data);
      } catch (_) {
        // Ignore — leave previous results visible.
      } finally {
        if (mounted) setState(() => _searchLoading = false);
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  Map<String, String> get _deptIdToDivipola {
    final out = <String, String>{};
    for (final d in _departments) {
      final code = d['divipola_code']?.toString();
      final id = d['id']?.toString();
      if (id != null && code != null && code.isNotEmpty) out[id] = code;
    }
    return out;
  }

  Map<String, double> get _divipolaToValue {
    final out = <String, double>{};
    final dataset = _mode == _Mode.price ? _priceData : _supplyData;
    final valueKey = _mode == _Mode.price ? 'avg_price' : 'total_kg';
    final lookup = _deptIdToDivipola;
    for (final row in dataset) {
      final code = lookup[row['department_id']?.toString()];
      if (code == null) continue;
      final v = (row[valueKey] as num?)?.toDouble() ?? 0.0;
      out[code] = v;
    }
    return out;
  }

  ({double minVal, double maxVal}) _minMax(Map<String, double> values) {
    final positive = values.values.where((v) => v > 0).toList();
    if (positive.isEmpty) return (minVal: 0, maxVal: 1);
    return (
      minVal: positive.reduce((a, b) => a < b ? a : b),
      maxVal: positive.reduce((a, b) => a > b ? a : b),
    );
  }

  List<Map<String, dynamic>> get _visibleMarkets {
    if (_activeMarketIds == null) return _allMarkets;
    return _allMarkets.where((m) => _activeMarketIds!.contains(m['id'])).toList();
  }

  // Ray-casting point-in-polygon — flutter_map's PolygonLayer doesn't
  // ship tap callbacks in 7.x, so we test against the rings ourselves
  // using `MapOptions.onTap`.
  bool _pointInRing(LatLng p, List<LatLng> ring) {
    var inside = false;
    final n = ring.length;
    for (var i = 0, j = n - 1; i < n; j = i++) {
      final xi = ring[i].longitude, yi = ring[i].latitude;
      final xj = ring[j].longitude, yj = ring[j].latitude;
      final intersect = ((yi > p.latitude) != (yj > p.latitude)) &&
          (p.longitude < (xj - xi) * (p.latitude - yi) / ((yj - yi) == 0 ? 1e-12 : (yj - yi)) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  void _onMapTap(LatLng tapped) {
    for (final poly in _polygons) {
      if (_pointInRing(tapped, poly.ring)) {
        _showDepartmentDialog(poly);
        return;
      }
    }
  }

  void _showDepartmentDialog(_DeptPolygon poly) {
    final t = context.read<SettingsProvider>().t;
    final value = _divipolaToValue[poly.divipola];
    final label = _mode == _Mode.price ? t.map_prices : t.map_supply;
    final hasValue = value != null && value > 0;
    final formatted = _mode == _Mode.price
        ? formatCOPCompact(value ?? 0)
        : formatKg(value ?? 0);
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(poly.name),
        content: Text('$label: ${hasValue ? formatted : t.map_no_data}'),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final t = context.watch<SettingsProvider>().t;
    final values = _divipolaToValue;
    final mm = _minMax(values);
    final colorScale = _mode == _Mode.price ? _kPriceColors : _kSupplyColors;

    final coloredPolygons = <Polygon>[];
    for (final poly in _polygons) {
      final v = values[poly.divipola];
      final fill = (v != null && v > 0)
          ? interpolateColor(v, mm.minVal, mm.maxVal, colorScale)
          : _kNoDataColor;
      coloredPolygons.add(Polygon(
        points: poly.ring,
        color: fill.withValues(alpha: 0.7),
        borderColor: const Color(0xFFFFFFFF),
        borderStrokeWidth: 1.5,
      ));
    }

    return Stack(
      children: [
        if (!_loading)
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _kColombiaCenter,
              initialZoom: _kColombiaZoom,
              onTap: (tapPos, point) => _onMapTap(point),
              interactionOptions: const InteractionOptions(
                flags: InteractiveFlag.pinchZoom |
                    InteractiveFlag.drag |
                    InteractiveFlag.doubleTapZoom |
                    InteractiveFlag.flingAnimation,
              ),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.agroamigo.iphone',
                maxNativeZoom: 19,
              ),
              PolygonLayer(polygons: coloredPolygons),
              MarkerLayer(
                markers: _visibleMarkets.map((m) {
                  final lat = (m['lat'] as num).toDouble();
                  final lng = (m['lng'] as num).toDouble();
                  return Marker(
                    point: LatLng(lat, lng),
                    width: 36,
                    height: 36,
                    child: GestureDetector(
                      onTap: () => _showMarketCallout(m),
                      child: const Icon(
                        CupertinoIcons.location_solid,
                        color: AppColors.primary,
                        size: 28,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        if (_loading)
          ColoredBox(
            color: AppColors.background,
            child: SizedBox.expand(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CupertinoActivityIndicator(radius: 16),
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    t.map_loading,
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: AppFontSize.md,
                    ),
                  ),
                ],
              ),
            ),
          ),

        // Top control panel.
        Positioned(
          top: AppSpacing.md,
          left: AppSpacing.md,
          right: AppSpacing.md,
          child: _buildControlPanel(t, mm.minVal, mm.maxVal, colorScale),
        ),

        // Bottom legend.
        if (!_loading)
          Positioned(
            bottom: AppSpacing.lg,
            left: AppSpacing.md,
            right: AppSpacing.md,
            child: _buildLegend(t, mm.minVal, mm.maxVal, colorScale),
          ),
      ],
    );
  }

  // ---------------------------------------------------------------------------
  // Control panel
  // ---------------------------------------------------------------------------

  Widget _buildControlPanel(
      Translations t, double minVal, double maxVal, List<Color> colorScale) {
    final hasProduct = _selectedProduct != null;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        boxShadow: const [
          BoxShadow(color: AppColors.shadow, blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Product selector.
          GestureDetector(
            onTap: () =>
                setState(() => _showProductPicker = !_showProductPicker),
            behavior: HitTestBehavior.opaque,
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: hasProduct
                    ? AppColors.primary.withValues(alpha: 0.05)
                    : AppColors.surface,
                borderRadius: BorderRadius.circular(AppRadius.md),
                border: Border.all(
                  color: hasProduct ? AppColors.primary : AppColors.borderLight,
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      hasProduct
                          ? (_selectedProduct!['canonical_name']?.toString() ??
                              t.map_all_products)
                          : t.map_all_products,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppFontSize.sm,
                        fontWeight: FontWeight.w500,
                        color: hasProduct
                            ? AppColors.primary
                            : AppColors.textSecondary,
                      ),
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_down,
                    size: 14,
                    color: hasProduct
                        ? AppColors.primary
                        : AppColors.textSecondary,
                  ),
                ],
              ),
            ),
          ),

          if (_showProductPicker) ...[
            const SizedBox(height: AppSpacing.sm),
            _buildProductDropdown(t),
          ],

          // Presentation chips — only when product picked, mode=price, list non-empty.
          if (hasProduct && _mode == _Mode.price && _presentations.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            SizedBox(
              height: 32,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _presentations.length,
                separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.xs),
                itemBuilder: (_, i) {
                  final p = _presentations[i];
                  final selected = _selectedPresentation != null &&
                      _selectedPresentation!['presentation_id'] == p['presentation_id'] &&
                      _selectedPresentation!['units_id'] == p['units_id'];
                  return GestureDetector(
                    onTap: () {
                      setState(() => _selectedPresentation = p);
                      _loadMapData();
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.sm,
                        vertical: AppSpacing.xs,
                      ),
                      decoration: BoxDecoration(
                        color: selected ? AppColors.primary : AppColors.surface,
                        borderRadius: BorderRadius.circular(AppRadius.full),
                        border: Border.all(
                          color: selected ? AppColors.primary : AppColors.borderLight,
                        ),
                      ),
                      child: Center(
                        child: Text(
                          p['label']?.toString() ?? '',
                          style: TextStyle(
                            fontSize: AppFontSize.xs,
                            color: selected
                                ? AppColors.textInverse
                                : AppColors.textSecondary,
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],

          const SizedBox(height: AppSpacing.sm),
          // Mode toggle.
          Row(
            children: [
              Expanded(child: _modeButton(t.map_prices, CupertinoIcons.money_dollar_circle, _Mode.price)),
              const SizedBox(width: AppSpacing.sm),
              Expanded(child: _modeButton(t.map_supply, CupertinoIcons.chart_bar_alt_fill, _Mode.supply)),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            (hasProduct ? '${_selectedProduct!['canonical_name']} — ' : '') +
                (_mode == _Mode.price ? t.map_price_legend : t.map_supply_legend),
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: AppFontSize.xs,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _modeButton(String label, IconData icon, _Mode mode) {
    final active = _mode == mode;
    return GestureDetector(
      onTap: () {
        if (_mode == mode) return;
        setState(() => _mode = mode);
        _loadPresentations().then((_) => _loadMapData());
      },
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : AppColors.borderLight,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 16,
              color: active ? AppColors.textInverse : AppColors.textSecondary,
            ),
            const SizedBox(width: AppSpacing.xs),
            Text(
              label,
              style: TextStyle(
                fontSize: AppFontSize.sm,
                fontWeight: FontWeight.w600,
                color: active ? AppColors.textInverse : AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProductDropdown(Translations t) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.sm),
            child: CupertinoSearchTextField(
              controller: _searchController,
              placeholder: t.map_search_product,
              onChanged: _onSearchChanged,
              autofocus: true,
            ),
          ),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 220),
            child: SingleChildScrollView(
              child: Column(
                children: [
                  _pickerItem(
                    label: t.map_all_products,
                    selected: _selectedProduct == null,
                    onTap: () {
                      setState(() {
                        _selectedProduct = null;
                        _showProductPicker = false;
                        _productSearch = '';
                        _searchController.clear();
                        _productResults = const [];
                        _presentations = const [];
                        _selectedPresentation = null;
                      });
                      _loadMapData();
                    },
                  ),
                  if (_searchLoading)
                    const Padding(
                      padding: EdgeInsets.all(AppSpacing.md),
                      child: CupertinoActivityIndicator(),
                    ),
                  ..._productResults.map((p) {
                    final id = p['id']?.toString();
                    final selected = _selectedProduct?['id'] == id;
                    final cat = ((p['dim_subcategory'] as Map?)?['dim_category']
                        as Map?)?['canonical_name']
                        ?.toString();
                    return _pickerItem(
                      label: p['canonical_name']?.toString() ?? '',
                      sublabel: cat,
                      selected: selected,
                      onTap: () {
                        setState(() {
                          _selectedProduct = p;
                          _showProductPicker = false;
                          _productSearch = '';
                          _searchController.clear();
                          _productResults = const [];
                        });
                        _loadPresentations().then((_) => _loadMapData());
                      },
                    );
                  }),
                  if (_productSearch.length >= 2 &&
                      !_searchLoading &&
                      _productResults.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(AppSpacing.md),
                      child: Text(
                        t.settings_no_results,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: AppFontSize.sm,
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _pickerItem({
    required String label,
    String? sublabel,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(
          vertical: AppSpacing.sm,
          horizontal: AppSpacing.md,
        ),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primary.withValues(alpha: 0.05)
              : AppColors.surface,
          border: const Border(
            bottom: BorderSide(color: AppColors.borderLight, width: 1),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: AppFontSize.sm,
                color: selected ? AppColors.primary : AppColors.textPrimary,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
            if (sublabel != null && sublabel.isNotEmpty)
              Text(
                sublabel,
                style: const TextStyle(
                  fontSize: AppFontSize.xs,
                  color: AppColors.textTertiary,
                ),
              ),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Legend
  // ---------------------------------------------------------------------------

  Widget _buildLegend(
      Translations t, double minVal, double maxVal, List<Color> colorScale) {
    final hasProduct = _selectedProduct != null;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        boxShadow: const [
          BoxShadow(color: AppColors.shadow, blurRadius: 8, offset: Offset(0, -2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (hasProduct)
            Wrap(
              alignment: WrapAlignment.center,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                _legendSwatch(colorScale[0]),
                Text(
                  _mode == _Mode.price ? formatCOPCompact(minVal) : formatKg(minVal),
                  style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    color: AppColors.textSecondary,
                  ),
                ),
                _legendSwatch(colorScale[3]),
                _legendSwatch(colorScale[6]),
                Text(
                  _mode == _Mode.price ? formatCOPCompact(maxVal) : formatKg(maxVal),
                  style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    color: AppColors.textSecondary,
                  ),
                ),
                _legendSwatch(_kNoDataColor),
                Text(
                  t.map_no_data,
                  style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            )
          else
            Text(
              t.map_pick_product_prompt,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: AppFontSize.sm,
                color: AppColors.textSecondary,
              ),
            ),
          const SizedBox(height: 2),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                t.map_source,
                style: const TextStyle(
                  fontSize: AppFontSize.xs,
                  color: AppColors.textTertiary,
                ),
              ),
              if (hasProduct) ...[
                const SizedBox(width: AppSpacing.md),
                Text(
                  '${_visibleMarkets.length} mercados',
                  style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    fontWeight: FontWeight.w600,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ],
          ),
          if (hasProduct)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                t.map_no_highlight_note,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: AppFontSize.xs,
                  fontStyle: FontStyle.italic,
                  color: AppColors.textTertiary,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _legendSwatch(Color color) {
    return Container(
      width: 20,
      height: 12,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Market callout
  // ---------------------------------------------------------------------------

  void _showMarketCallout(Map<String, dynamic> market) {
    final name = market['name']?.toString() ?? '';
    final city = market['city']?.toString() ?? '';
    final dept = market['department']?.toString() ?? '';
    final id = market['id']?.toString();
    showCupertinoModalPopup<void>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: Text(name),
        message: Text('$city, $dept'),
        actions: [
          CupertinoActionSheetAction(
            onPressed: () {
              Navigator.of(ctx).pop();
              if (id == null) return;
              Navigator.of(context).push(
                CupertinoPageRoute(
                  builder: (_) => MarketDetailScreen(marketId: id),
                ),
              );
            },
            child: const Text('Ver detalles'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Cerrar'),
        ),
      ),
    );
  }
}
