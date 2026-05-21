import 'package:agroamigo_iphone/services/supabase_client.dart';

/// Average price per department for a product+presentation (or all products
/// coarsely). Server-side aggregated — no row-cap bias. The presentation is
/// required when a product is given: mixing kg-vs-lb-vs-unit into one "avg"
/// is garbage, so the RPC enforces it and raises if omitted.
Future<List<Map<String, dynamic>>> getPricesByDepartment({
  String? productId,
  int days = 30,
  String? presentationId,
  String? unitsId,
}) async {
  if (productId != null && (presentationId == null || unitsId == null)) {
    throw Exception(
        'getPricesByDepartment: presentationId and unitsId are required when productId is provided');
  }
  final dynamic raw = productId != null
      ? await SupabaseService.client
          .rpc('get_prices_by_department_for_product', params: {
          'p_product_id': productId,
          'p_presentation_id': presentationId,
          'p_units_id': unitsId,
          'p_days': days,
        })
      : await SupabaseService.client
          .rpc('get_prices_by_department', params: {
          'p_product_id': null,
          'p_days': days,
          'p_presentation_id': null,
          'p_units_id': null,
        });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'department_id': row['department_id'],
      'avg_price': (row['avg_price'] as num? ?? 0).toDouble(),
      'observation_count': (row['observation_count'] as num? ?? 0).toInt(),
    };
  }).toList();
}

/// Total supply (kg) per destination department. Server-side GROUP BY.
Future<List<Map<String, dynamic>>> getSupplyByDepartment({
  String? productId,
  int days = 30,
}) async {
  final dynamic raw = productId != null
      ? await SupabaseService.client
          .rpc('get_supply_by_department_for_product', params: {
          'p_product_id': productId,
          'p_days': days,
        })
      : await SupabaseService.client.rpc('get_supply_by_department', params: {
          'p_product_id': null,
          'p_days': days,
        });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'department_id': row['department_id'],
      'total_kg': (row['total_kg'] as num? ?? 0).toDouble(),
    };
  }).toList();
}

/// Get department dimension data with DIVIPOLA codes.
Future<List<Map<String, dynamic>>> getDepartments() async {
  return SupabaseService.client
      .from('dim_department')
      .select('id, canonical_name, divipola_code')
      .order('canonical_name');
}

Future<List<Map<String, dynamic>>> getProductPresentationsForMap(
    String productId,
    {int days = 30}) async {
  final dynamic raw = await SupabaseService.client
      .rpc('get_product_presentations_for_map', params: {
    'p_product_id': productId,
    'p_days': days,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    final parts = [row['presentation_name'], row['units_name']]
        .whereType<String>()
        .toList();
    return <String, dynamic>{
      'presentation_id': row['presentation_id'],
      'units_id': row['units_id'],
      'label': parts.join(' \u00b7 '),
    };
  }).toList();
}

Future<List<String>> getMarketsWithProductData(
    String productId, String mode,
    {int days = 30,
    String? presentationId,
    String? unitsId}) async {
  if (mode == 'price') {
    final dynamic raw = await SupabaseService.client
        .rpc('get_price_markets_for_product', params: {
      'p_product_id': productId,
      'p_days': days,
      'p_presentation_id': presentationId,
      'p_units_id': unitsId,
    });
    return ((raw as List?) ?? []).map((r) {
      if (r is String) return r;
      return (r as Map<String, dynamic>)['get_price_markets_for_product']
          as String?;
    }).whereType<String>().toList();
  }
  final dynamic raw = await SupabaseService.client
      .rpc('get_supply_markets_for_product',
          params: {'p_product_id': productId, 'p_days': days});
  return ((raw as List?) ?? []).map((r) {
    if (r is String) return r;
    return (r as Map<String, dynamic>)['get_supply_markets_for_product']
        as String?;
  }).whereType<String>().toList();
}

/// Get market locations by joining market → city → divipola_municipios for lat/lng.
Future<List<Map<String, dynamic>>> getMarketLocations() async {
  final markets = await SupabaseService.client.from('dim_market').select('''
    id, canonical_name, sipsa_id,
    dim_city!inner(
      id, canonical_name, divipola_code, department_id,
      dim_department!inner(id, canonical_name, divipola_code)
    )
  ''');

  final divCodes = markets
      .map((m) {
        final city = m['dim_city'] as Map<String, dynamic>?;
        return city?['divipola_code'] as String?;
      })
      .whereType<String>()
      .toList();

  if (divCodes.isEmpty) {
    return markets
        .map((m) => <String, dynamic>{...m, 'lat': null, 'lng': null})
        .toList();
  }

  final municipios = await SupabaseService.client
      .from('divipola_municipios')
      .select('codigo_municipio, latitud, longitud')
      .in_('codigo_municipio', divCodes);

  final coordMap = <String, Map<String, double>>{};
  for (final m in municipios) {
    final lat = m['latitud'];
    final lng = m['longitud'];
    final code = m['codigo_municipio'] as String?;
    if (lat != null && lng != null && code != null) {
      coordMap[code] = {
        'lat': (lat as num).toDouble(),
        'lng': (lng as num).toDouble(),
      };
    }
  }

  return markets.map((m) {
    final city = m['dim_city'] as Map<String, dynamic>?;
    final dept = city?['dim_department'] as Map<String, dynamic>?;
    final code = city?['divipola_code'] as String?;
    final coords = code != null ? coordMap[code] : null;
    return <String, dynamic>{
      'id': m['id'],
      'name': m['canonical_name'],
      'city': city?['canonical_name'],
      'department': dept?['canonical_name'],
      'dept_divipola': dept?['divipola_code'],
      'lat': coords?['lat'],
      'lng': coords?['lng'],
    };
  }).toList();
}
