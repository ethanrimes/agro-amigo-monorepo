import { supabase } from '../lib/supabase';

export async function getCategories() {
  const { data, error } = await supabase
    .from('dim_category')
    .select('id, canonical_name, sipsa_id')
    .order('canonical_name');
  if (error) throw error;
  return data;
}

export async function getSubcategories(categoryId?: string) {
  let query = supabase
    .from('dim_subcategory')
    .select('id, canonical_name, category_id')
    .order('canonical_name');
  if (categoryId) query = query.eq('category_id', categoryId);
  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function getProducts(options?: {
  categoryId?: string;
  subcategoryId?: string;
  search?: string;
  limit?: number;
}) {
  let query = supabase
    .from('dim_product')
    .select(`
      id, canonical_name, subcategory_id, cpc_code, sipsa_id,
      dim_subcategory!inner(
        id, canonical_name, category_id,
        dim_category!inner(id, canonical_name)
      )
    `)
    .order('canonical_name')
    .limit(options?.limit ?? 50);

  if (options?.search) {
    query = query.ilike('canonical_name', `%${options.search}%`);
  }
  if (options?.subcategoryId) {
    query = query.eq('subcategory_id', options.subcategoryId);
  }
  if (options?.categoryId) {
    query = query.eq('dim_subcategory.category_id', options.categoryId);
  }
  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function getProductById(id: string) {
  const { data, error } = await supabase
    .from('dim_product')
    .select(`
      id, canonical_name, subcategory_id, cpc_code, sipsa_id,
      dim_subcategory(
        id, canonical_name, category_id,
        dim_category(id, canonical_name)
      )
    `)
    .eq('id', id)
    .single();
  if (error) throw error;
  return data;
}

export async function getProductPrices(productId: string, options?: {
  marketId?: string;
  days?: number;
  limit?: number;
}) {
  const days = options?.days ?? 30;

  let query = supabase
    .from('price_observations')
    .select(`
      price_date, min_price, max_price, avg_price, market_id,
      presentation_id, units_id,
      dim_market(id, canonical_name, dim_city(canonical_name)),
      dim_presentation(id, canonical_name),
      dim_units(id, canonical_name)
    `)
    .eq('product_id', productId)
    .order('price_date', { ascending: false })
    .limit(options?.limit ?? 500);

  if (days > 0) {
    const since = new Date();
    since.setDate(since.getDate() - days);
    query = query.gte('price_date', since.toISOString().split('T')[0]);
  }

  if (options?.marketId) {
    query = query.eq('market_id', options.marketId);
  }

  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function getProductPricesByMarket(productId: string, limit = 100) {
  const twoWeeksAgo = new Date();
  twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 14);

  const { data, error } = await supabase
    .from('price_observations')
    .select(`
      price_date, min_price, max_price, avg_price,
      market_id, presentation_id, units_id,
      dim_market(id, canonical_name, dim_city(canonical_name)),
      dim_presentation(id, canonical_name),
      dim_units(id, canonical_name)
    `)
    .eq('product_id', productId)
    .gte('price_date', twoWeeksAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data;
}

export async function getLatestPrices(productIds: string[], limit = 1) {
  const { data, error } = await supabase
    .from('price_observations')
    .select('product_id, price_date, min_price, max_price, avg_price')
    .in('product_id', productIds)
    .order('price_date', { ascending: false })
    .limit(limit * productIds.length);
  if (error) throw error;
  return data;
}

export async function getWatchlistPrices(productIds: string[], marketId?: string | null) {
  if (productIds.length === 0) return [];
  const twoWeeksAgo = new Date();
  twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 14);

  const base = () => supabase
    .from('price_observations')
    .select(`
      product_id, price_date, min_price, max_price, avg_price,
      market_id, presentation_id, units_id,
      dim_market(id, canonical_name),
      dim_presentation(id, canonical_name),
      dim_units(id, canonical_name),
      dim_product!inner(id, canonical_name)
    `)
    .in('product_id', productIds)
    .gte('price_date', twoWeeksAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false });

  // Prefer rows from the user's default market. Fall back to national
  // observations for any watchlist item that has no data in that market.
  // Tag each row with _from_default so the UI can distinguish "Corabastos"
  // (specific market) from "Promedio nacional" (fallback).
  if (marketId) {
    const { data: mkt, error: e1 } = await base().eq('market_id', marketId).limit(productIds.length * 5);
    if (e1) throw e1;
    const covered = new Set((mkt || []).map((r: any) => r.product_id));
    const missing = productIds.filter(id => !covered.has(id));
    const tagged = (mkt || []).map((r: any) => ({ ...r, _from_default: true }));
    if (missing.length > 0) {
      const { data: nat, error: e2 } = await base().in('product_id', missing).limit(missing.length * 5);
      if (e2) throw e2;
      return [...tagged, ...(nat || []).map((r: any) => ({ ...r, _from_default: false }))];
    }
    return tagged;
  }

  const { data, error } = await base().limit(productIds.length * 5);
  if (error) throw error;
  // No default market set — everything is national.
  return (data || []).map((r: any) => ({ ...r, _from_default: false }));
}

export async function getTrendingProducts(limit = 10, marketId?: string) {
  // Home-screen "Top Increases/Decreases" is labeled "last 7 days", so we
  // only fetch that window — don't over-pull.
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);

  let query = supabase
    .from('price_observations')
    .select(`
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
    `)
    .gte('price_date', weekAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(limit);
  if (marketId) query = query.eq('market_id', marketId);
  const { data, error } = await query;
  if (error) throw error;
  return data;
}
