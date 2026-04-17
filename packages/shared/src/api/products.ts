import { getSupabaseClient } from '../lib/supabase';

export async function getCategories() {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('dim_category')
    .select('id, canonical_name, sipsa_id')
    .order('canonical_name');
  if (error) throw error;
  return data;
}

export async function getSubcategories(categoryId?: string) {
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
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
  presentationId?: string;
  unitsId?: string;
  days?: number;
  limit?: number;
}) {
  const supabase = getSupabaseClient();
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
    .limit(options?.limit ?? 1000);

  if (days > 0) {
    const since = new Date();
    since.setDate(since.getDate() - days);
    query = query.gte('price_date', since.toISOString().split('T')[0]);
  }

  if (options?.marketId) {
    query = query.eq('market_id', options.marketId);
  }

  if (options?.presentationId) {
    query = query.eq('presentation_id', options.presentationId);
  }

  if (options?.unitsId) {
    query = query.eq('units_id', options.unitsId);
  }

  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function getProductPricesByMarket(productId: string, limit = 100) {
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('price_observations')
    .select('product_id, price_date, min_price, max_price, avg_price')
    .in('product_id', productIds)
    .order('price_date', { ascending: false })
    .limit(limit * productIds.length);
  if (error) throw error;
  return data;
}

export async function getWatchlistPrices(productIds: string[]) {
  if (productIds.length === 0) return [];
  const supabase = getSupabaseClient();
  const twoWeeksAgo = new Date();
  twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 14);

  const { data, error } = await supabase
    .from('price_observations')
    .select(`
      product_id, price_date, min_price, max_price, avg_price,
      market_id, presentation_id, units_id,
      dim_market(id, canonical_name, dim_city(canonical_name)),
      dim_presentation(id, canonical_name),
      dim_units(id, canonical_name),
      dim_product!inner(id, canonical_name)
    `)
    .in('product_id', productIds)
    .gte('price_date', twoWeeksAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(productIds.length * 5);

  if (error) throw error;
  return data;
}

export async function getTrendingProducts(limit = 10) {
  const supabase = getSupabaseClient();
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);

  const { data, error } = await supabase
    .from('price_observations')
    .select(`
      product_id,
      min_price,
      max_price,
      avg_price,
      price_date,
      presentation_id,
      dim_product!inner(id, canonical_name, subcategory_id),
      dim_presentation(canonical_name)
    `)
    .gte('price_date', weekAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data;
}
