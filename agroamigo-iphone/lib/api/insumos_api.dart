import 'dart:math';

import 'package:agroamigo_iphone/services/supabase_client.dart';

Future<List<Map<String, dynamic>>> getInsumoGrupos() async {
  return SupabaseService.client
      .from('dim_insumo_grupo')
      .select('id, canonical_name')
      .order('canonical_name');
}

Future<List<Map<String, dynamic>>> getInsumoSubgrupos(
    {String? grupoId}) async {
  var query = SupabaseService.client
      .from('dim_insumo_subgrupo')
      .select('id, canonical_name, grupo_id');
  if (grupoId != null) query = query.eq('grupo_id', grupoId);
  return query.order('canonical_name');
}

Future<List<Map<String, dynamic>>> getInsumos({
  String? grupoId,
  String? subgrupoId,
  String? search,
  int limit = 50,
}) async {
  const select =
      'id, canonical_name, grupo, subgrupo, cpc_code, cpc_id, grupo_id, subgrupo_id';

  var q = SupabaseService.client.from('dim_insumo').select(select);
  if (search != null) q = q.ilike('canonical_name', '%$search%');
  if (grupoId != null) q = q.eq('grupo_id', grupoId);
  if (subgrupoId != null) q = q.eq('subgrupo_id', subgrupoId);

  final results = List<Map<String, dynamic>>.from(
    await q.order('canonical_name').limit(limit),
  );

  // Paginate if we hit PostgREST row limit
  if (results.length >= 1000 && limit > 1000) {
    final pages = (limit / 1000).ceil();
    for (int page = 1; page < pages; page++) {
      try {
        var pq = SupabaseService.client.from('dim_insumo').select(select);
        if (search != null) pq = pq.ilike('canonical_name', '%$search%');
        if (grupoId != null) pq = pq.eq('grupo_id', grupoId);
        if (subgrupoId != null) pq = pq.eq('subgrupo_id', subgrupoId);
        final pageData = await pq
            .order('canonical_name')
            .range(page * 1000, min((page + 1) * 1000 - 1, limit - 1));
        if (pageData.isEmpty) break;
        results.addAll(pageData);
      } catch (e) {
        print('getInsumos pagination failed at page $page: $e');
        break;
      }
    }
  }

  return results;
}

Future<Map<String, dynamic>> getInsumoById(String id) async {
  return SupabaseService.client
      .from('dim_insumo')
      .select(
          'id, canonical_name, grupo, subgrupo, cpc_code, cpc_id, grupo_id, subgrupo_id')
      .eq('id', id)
      .single();
}

/// Get all CPC codes that have at least one insumo linked.
/// Uses server-side RPC to bypass PostgREST row limits.
Future<List<dynamic>> getInsumoCpcTree() async {
  final data = await SupabaseService.client.rpc('get_insumo_cpc_tree');
  return (data as List?) ?? [];
}

Future<String> getCpcTitle(String cpcCode) async {
  try {
    final data = await SupabaseService.client
        .from('dim_cpc')
        .select('title')
        .eq('code', cpcCode)
        .single();
    return data['title'] as String? ?? '';
  } catch (_) {
    return '';
  }
}

Future<List<dynamic>> getCpcLatestPrices(String cpcCode) async {
  final data = await SupabaseService.client.rpc(
      'get_cpc_latest_dept_prices',
      params: {'p_cpc_code': cpcCode});
  return (data as List?) ?? [];
}

/// Same shape as getCpcLatestPrices but scoped to a subgrupo. Used when an
/// insumo has no CPC code — the UI falls back to comparing against all
/// articles in the same subgrupo.
Future<List<dynamic>> getSubgrupoLatestPrices(String subgrupoId) async {
  final data = await SupabaseService.client.rpc(
      'get_subgrupo_latest_dept_prices',
      params: {'p_subgrupo_id': subgrupoId});
  return (data as List?) ?? [];
}

Future<List<Map<String, dynamic>>> getInsumoPricesByDepartment(
    String insumoId,
    {int limit = 200}) async {
  return SupabaseService.client
      .from('insumo_prices_department')
      .select('''
        price_date, avg_price, department_id, presentation,
        dim_department!inner(id, canonical_name)
      ''')
      .eq('insumo_id', insumoId)
      .order('price_date', ascending: false)
      .limit(limit);
}

/// One stable row per insumo (latest observation with its presentation).
Future<List<Map<String, dynamic>>> getWatchlistInsumoPrices(
    List<String> insumoIds) async {
  if (insumoIds.isEmpty) return [];
  final data = await SupabaseService.client.rpc(
      'get_watchlist_insumo_latest_prices',
      params: {'p_insumo_ids': insumoIds, 'p_days': 180});
  // Match the shape the home screen already expects: dim_department nested.
  return ((data as List?) ?? []).map((r) {
    final row = r as Map<String, dynamic>;
    return <String, dynamic>{
      'insumo_id': row['insumo_id'],
      'price_date': row['price_date'],
      'avg_price': (row['avg_price'] as num? ?? 0).toDouble(),
      'presentation': row['presentation'],
      'dim_department': {
        'id': row['department_id'],
        'canonical_name': row['dept_name'],
      },
    };
  }).toList();
}

Future<List<Map<String, dynamic>>> getInsumoPricesByMunicipality(
    String insumoId,
    {String? departmentId,
    int limit = 200}) async {
  var query = SupabaseService.client
      .from('insumo_prices_municipality')
      .select('''
        price_date, avg_price, department_id, city_id, presentation,
        dim_department!inner(id, canonical_name),
        dim_city(id, canonical_name)
      ''')
      .eq('insumo_id', insumoId);
  if (departmentId != null) query = query.eq('department_id', departmentId);
  return query.order('price_date', ascending: false).limit(limit);
}
