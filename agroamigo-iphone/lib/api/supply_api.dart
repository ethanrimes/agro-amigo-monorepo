import 'package:agroamigo_iphone/services/supabase_client.dart';
import 'package:agroamigo_iphone/api/_types.dart';

Future<Map<String, dynamic>?> getProductSupplySummary(
  String productId,
  int days, {
  String? marketId,
  String? provDept,
}) async {
  final dynamic raw = await SupabaseService.client
      .rpc('get_product_supply_summary', params: {
    'p_product_id': productId,
    'p_days': days,
    'p_market_id': marketId,
    'p_prov_dept': provDept,
  });
  final row = (raw is List) ? (raw.isEmpty ? null : raw[0]) : raw;
  if (row == null) return null;
  return Map<String, dynamic>.from(row as Map);
}

Future<List<Map<String, dynamic>>> getProductTopDestinations(
  String productId,
  int days, {
  String? provDept,
  int limit = 15,
}) async {
  final dynamic raw = await SupabaseService.client
      .rpc('get_product_top_destinations', params: {
    'p_product_id': productId,
    'p_days': days,
    'p_prov_dept': provDept,
    'p_limit': limit,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'market_id': row['market_id'],
      'market_name': row['market_name'],
      'total_kg': (row['total_kg'] as num? ?? 0).toDouble(),
      'newest_obs': row['newest_obs'],
    };
  }).toList();
}

Future<List<Map<String, dynamic>>> getProductTopOrigins(
  String productId,
  int days, {
  String? marketId,
  int limit = 15,
}) async {
  final dynamic raw =
      await SupabaseService.client.rpc('get_product_top_origins', params: {
    'p_product_id': productId,
    'p_days': days,
    'p_market_id': marketId,
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

Future<List<Map<String, dynamic>>> getProductSupplyByDate(
  String productId,
  int days, {
  String? marketId,
  String? provDept,
}) async {
  final dynamic raw = await SupabaseService.client
      .rpc('get_product_supply_by_date', params: {
    'p_product_id': productId,
    'p_days': days,
    'p_market_id': marketId,
    'p_prov_dept': provDept,
  });
  return ((raw as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'date': row['observation_date'],
      'kg': (row['total_kg'] as num? ?? 0).toDouble(),
    };
  }).toList();
}

Future<List<Map<String, dynamic>>> getTopSuppliedProducts(
    {int limit = 10}) async {
  final weekAgo = DateTime.now()
      .subtract(const Duration(days: 7))
      .toIso8601String()
      .split('T')
      .first;
  final data = await SupabaseService.client
      .from('supply_observations')
      .select(
          'product_id, quantity_kg, observation_date, dim_product!inner(canonical_name)')
      .gte('observation_date', weekAgo)
      .order('quantity_kg', ascending: false)
      .limit(500);

  final map = <String, Map<String, dynamic>>{};
  for (final row in data) {
    final pid = row['product_id'] as String;
    final name = (row['dim_product'] as Map<String, dynamic>?)
            ?['canonical_name'] as String? ??
        'Desconocido';
    final kg = (row['quantity_kg'] as num? ?? 0).toDouble();
    final obsDate = row['observation_date'] as String?;
    if (map.containsKey(pid)) {
      map[pid]!['total_kg'] = (map[pid]!['total_kg'] as double) + kg;
      final existing = map[pid]!['newest_obs'] as String?;
      if (obsDate != null &&
          (existing == null || obsDate.compareTo(existing) > 0)) {
        map[pid]!['newest_obs'] = obsDate;
      }
    } else {
      map[pid] = {
        'product_id': pid,
        'name': name,
        'total_kg': kg,
        'newest_obs': obsDate,
      };
    }
  }

  final sorted = map.values.toList()
    ..sort((a, b) =>
        (b['total_kg'] as double).compareTo(a['total_kg'] as double));
  return sorted.take(limit).toList();
}
