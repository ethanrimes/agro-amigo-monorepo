import 'package:agroamigo_iphone/services/supabase_client.dart';

Future<List<Map<String, dynamic>>> getCategories() async {
  return SupabaseService.client
      .from('dim_category')
      .select('id, canonical_name, sipsa_id')
      .order('canonical_name');
}

Future<List<Map<String, dynamic>>> getSubcategories(
    {String? categoryId}) async {
  var query = SupabaseService.client
      .from('dim_subcategory')
      .select('id, canonical_name, category_id');
  if (categoryId != null) query = query.eq('category_id', categoryId);
  return query.order('canonical_name');
}

Future<List<Map<String, dynamic>>> getProducts({
  String? categoryId,
  String? subcategoryId,
  String? search,
  int limit = 50,
}) async {
  var query = SupabaseService.client.from('dim_product').select('''
    id, canonical_name, subcategory_id, cpc_code, sipsa_id,
    dim_subcategory!inner(
      id, canonical_name, category_id,
      dim_category!inner(id, canonical_name)
    )
  ''');
  if (search != null) query = query.ilike('canonical_name', '%$search%');
  if (subcategoryId != null) query = query.eq('subcategory_id', subcategoryId);
  if (categoryId != null) {
    query = query.eq('dim_subcategory.category_id', categoryId);
  }
  return query.order('canonical_name').limit(limit);
}

Future<Map<String, dynamic>> getProductById(String id) async {
  return SupabaseService.client
      .from('dim_product')
      .select('''
        id, canonical_name, subcategory_id, cpc_code, sipsa_id,
        dim_subcategory(
          id, canonical_name, category_id,
          dim_category(id, canonical_name)
        )
      ''')
      .eq('id', id)
      .single();
}

Future<List<Map<String, dynamic>>> getProductPrices(
  String productId, {
  String? marketId,
  int days = 30,
  int limit = 500,
}) async {
  var query = SupabaseService.client.from('price_observations').select('''
    price_date, min_price, max_price, avg_price, market_id,
    presentation_id, units_id,
    dim_market(id, canonical_name, dim_city(canonical_name)),
    dim_presentation(id, canonical_name),
    dim_units(id, canonical_name)
  ''').eq('product_id', productId);
  if (days > 0) {
    final since = DateTime.now()
        .subtract(Duration(days: days))
        .toIso8601String()
        .split('T')
        .first;
    query = query.gte('price_date', since);
  }
  if (marketId != null) query = query.eq('market_id', marketId);
  return query.order('price_date', ascending: false).limit(limit);
}

Future<List<Map<String, dynamic>>> getProductPricesByMarket(
    String productId,
    {int limit = 100}) async {
  final twoWeeksAgo = DateTime.now()
      .subtract(const Duration(days: 14))
      .toIso8601String()
      .split('T')
      .first;
  return SupabaseService.client
      .from('price_observations')
      .select('''
        price_date, min_price, max_price, avg_price,
        market_id, presentation_id, units_id,
        dim_market(id, canonical_name, dim_city(canonical_name)),
        dim_presentation(id, canonical_name),
        dim_units(id, canonical_name)
      ''')
      .eq('product_id', productId)
      .gte('price_date', twoWeeksAgo)
      .order('price_date', ascending: false)
      .limit(limit);
}

Future<List<Map<String, dynamic>>> getLatestPrices(List<String> productIds,
    {int limit = 1}) async {
  return SupabaseService.client
      .from('price_observations')
      .select('product_id, price_date, min_price, max_price, avg_price')
      .in_('product_id', productIds)
      .order('price_date', ascending: false)
      .limit(limit * productIds.length);
}

/// Prefer rows from the user's default market. Fall back to national
/// observations for any watchlist item that has no data in that market.
/// Tags each row with _from_default so the UI can distinguish specific market
/// from "Promedio nacional" (fallback).
Future<List<Map<String, dynamic>>> getWatchlistPrices(
    List<String> productIds,
    {String? marketId}) async {
  if (productIds.isEmpty) return [];
  final twoWeeksAgo = DateTime.now()
      .subtract(const Duration(days: 14))
      .toIso8601String()
      .split('T')
      .first;

  const selectStr = '''
    product_id, price_date, min_price, max_price, avg_price,
    market_id, presentation_id, units_id,
    dim_market(id, canonical_name),
    dim_presentation(id, canonical_name),
    dim_units(id, canonical_name),
    dim_product!inner(id, canonical_name)
  ''';

  if (marketId != null) {
    final mkt = await SupabaseService.client
        .from('price_observations')
        .select(selectStr)
        .in_('product_id', productIds)
        .gte('price_date', twoWeeksAgo)
        .eq('market_id', marketId)
        .order('price_date', ascending: false)
        .limit(productIds.length * 5);

    final covered = mkt.map((r) => r['product_id'] as String).toSet();
    final missing = productIds.where((id) => !covered.contains(id)).toList();

    final tagged = mkt
        .map((r) => <String, dynamic>{...r, '_from_default': true})
        .toList();

    if (missing.isNotEmpty) {
      final nat = await SupabaseService.client
          .from('price_observations')
          .select(selectStr)
          .in_('product_id', missing)
          .gte('price_date', twoWeeksAgo)
          .order('price_date', ascending: false)
          .limit(missing.length * 5);
      return [
        ...tagged,
        ...nat.map((r) => <String, dynamic>{...r, '_from_default': false}),
      ];
    }
    return tagged;
  }

  // No default market set — everything is national.
  final data = await SupabaseService.client
      .from('price_observations')
      .select(selectStr)
      .in_('product_id', productIds)
      .gte('price_date', twoWeeksAgo)
      .order('price_date', ascending: false)
      .limit(productIds.length * 5);
  return data
      .map((r) => <String, dynamic>{...r, '_from_default': false})
      .toList();
}

Future<List<Map<String, dynamic>>> getTrendingProducts(
    {int limit = 10, String? marketId}) async {
  final weekAgo = DateTime.now()
      .subtract(const Duration(days: 7))
      .toIso8601String()
      .split('T')
      .first;
  var query = SupabaseService.client.from('price_observations').select('''
    product_id,
    market_id,
    min_price,
    max_price,
    avg_price,
    price_date,
    presentation_id,
    dim_product!inner(id, canonical_name, subcategory_id),
    dim_presentation(canonical_name),
    dim_market(canonical_name)
  ''').gte('price_date', weekAgo);
  if (marketId != null) query = query.eq('market_id', marketId);
  return query.order('price_date', ascending: false).limit(limit);
}
