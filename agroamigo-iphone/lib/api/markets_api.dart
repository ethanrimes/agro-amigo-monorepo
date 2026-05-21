import 'package:agroamigo_iphone/services/supabase_client.dart';
import 'package:agroamigo_iphone/api/_types.dart';

Future<List<Map<String, dynamic>>> getMarkets() async {
  return SupabaseService.client.from('dim_market').select('''
    id, canonical_name, city_id, sipsa_id,
    dim_city!inner(
      id, canonical_name, department_id,
      dim_department!inner(id, canonical_name)
    )
  ''').order('canonical_name');
}

Future<Map<String, dynamic>> getMarketById(String id) async {
  return SupabaseService.client
      .from('dim_market')
      .select('''
        id, canonical_name, city_id, sipsa_id,
        dim_city(
          id, canonical_name, department_id,
          dim_department(id, canonical_name)
        )
      ''')
      .eq('id', id)
      .single();
}

Future<List<Map<String, dynamic>>> getMarketProducts(String marketId,
    {int limit = 50}) async {
  final twoWeeksAgo = DateTime.now()
      .subtract(const Duration(days: 14))
      .toIso8601String()
      .split('T')
      .first;
  return SupabaseService.client
      .from('price_observations')
      .select('''
        product_id,
        min_price, max_price, avg_price, price_date,
        presentation_id, units_id,
        dim_product!inner(
          id, canonical_name, subcategory_id,
          dim_subcategory!inner(
            id, canonical_name, category_id,
            dim_category!inner(id, canonical_name)
          )
        ),
        dim_presentation(id, canonical_name),
        dim_units(id, canonical_name)
      ''')
      .eq('market_id', marketId)
      .gte('price_date', twoWeeksAgo)
      .order('price_date', ascending: false)
      .limit(limit);
}

Future<Map<String, dynamic>?> getMarketSupplySummary(
  String marketId,
  int days, {
  String? productId,
  String? provDept,
}) async {
  final dynamic raw =
      await SupabaseService.client.rpc('get_market_supply_summary', params: {
    'p_market_id': marketId,
    'p_days': days,
    'p_product_id': productId,
    'p_prov_dept': provDept,
  });
  final row = (raw is List) ? (raw.isEmpty ? null : raw[0]) : raw;
  if (row == null) return null;
  return Map<String, dynamic>.from(row as Map);
}

Future<List<Map<String, dynamic>>> getMarketTopProducts(
  String marketId,
  int days, {
  String? provDept,
  int limit = 10,
}) async {
  final dynamic raw =
      await SupabaseService.client.rpc('get_market_top_products', params: {
    'p_market_id': marketId,
    'p_days': days,
    'p_prov_dept': provDept,
    'p_limit': limit,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'product_id': row['product_id'],
      'product_name': row['product_name'],
      'total_kg': (row['total_kg'] as num? ?? 0).toDouble(),
      'newest_obs': row['newest_obs'],
    };
  }).toList();
}

Future<List<Map<String, dynamic>>> getMarketTopProvenance(
  String marketId,
  int days, {
  String? productId,
  int limit = 15,
}) async {
  final dynamic raw =
      await SupabaseService.client.rpc('get_market_top_provenance', params: {
    'p_market_id': marketId,
    'p_days': days,
    'p_product_id': productId,
    'p_limit': limit,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'dept_name': row['dept_name'],
      'total_kg': (row['total_kg'] as num? ?? 0).toDouble(),
      'newest_obs': row['newest_obs'],
    };
  }).toList();
}

/// Paginated fetch — a single market can have tens of thousands of supply rows
/// over a year, far above PostgREST's 1000-row response cap.
Future<List<Map<String, dynamic>>> getMarketSupply(String marketId,
    {int days = 30}) async {
  const pageSize = 1000;
  const maxRows = 100000;
  String? sinceStr;
  if (days > 0) {
    sinceStr = DateTime.now()
        .subtract(Duration(days: days))
        .toIso8601String()
        .split('T')
        .first;
  }
  final all = <Map<String, dynamic>>[];
  for (int off = 0; off < maxRows; off += pageSize) {
    var q = SupabaseService.client
        .from('supply_observations')
        .select(
            'observation_date, quantity_kg, product_id, provenance_dept_name, provenance_muni_name, dim_product(canonical_name)')
        .eq('market_id', marketId);
    if (sinceStr != null) q = q.gte('observation_date', sinceStr);
    final batch = await q
        .order('observation_date', ascending: false)
        .range(off, off + pageSize - 1);
    all.addAll(batch);
    if (batch.length < pageSize) break;
  }
  return all;
}

/// For each (product, presentation, units), returns the per-market average of
/// the latest observation in the window. Server-side — no row-cap bias.
Future<List<Map<String, dynamic>>> getNationalPriceAverages(
    List<String> productIds,
    {int days = 30}) async {
  if (productIds.isEmpty) return [];
  final dynamic raw = await SupabaseService.client
      .rpc('get_national_price_averages', params: {
    'p_product_ids': productIds,
    'p_days': days,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'product_id': row['product_id'],
      'presentation_id': row['presentation_id'],
      'units_id': row['units_id'],
      'avg_price': (row['avg_price'] as num? ?? 0).round(),
      'price_date': row['price_date'],
      'market_count': (row['market_count'] as num? ?? 0).toInt(),
    };
  }).toList();
}

/// Returns avg kg per market (across the markets that carry the product) for
/// each product. Field name `quantity_kg` preserved for caller compatibility.
Future<List<Map<String, dynamic>>> getNationalSupplyAverages(
    List<String> productIds,
    {int days = 30}) async {
  if (productIds.isEmpty) return [];
  final dynamic raw = await SupabaseService.client
      .rpc('get_national_supply_averages', params: {
    'p_product_ids': productIds,
    'p_days': days,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'product_id': row['product_id'],
      'quantity_kg': (row['avg_kg_per_market'] as num? ?? 0).toDouble(),
      'total_kg': (row['total_kg'] as num? ?? 0).toDouble(),
      'market_count': (row['market_count'] as num? ?? 0).toInt(),
    };
  }).toList();
}
