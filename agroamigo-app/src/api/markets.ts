import { supabase } from '../lib/supabase';

export async function getMarkets() {
  const { data, error } = await supabase
    .from('dim_market')
    .select(`
      id, canonical_name, city_id, sipsa_id,
      dim_city!inner(
        id, canonical_name, department_id,
        dim_department!inner(id, canonical_name)
      )
    `)
    .order('canonical_name');
  if (error) throw error;
  return data;
}

export async function getMarketById(id: string) {
  const { data, error } = await supabase
    .from('dim_market')
    .select(`
      id, canonical_name, city_id, sipsa_id,
      dim_city(
        id, canonical_name, department_id,
        dim_department(id, canonical_name)
      )
    `)
    .eq('id', id)
    .single();
  if (error) throw error;
  return data;
}

export async function getMarketProducts(marketId: string, limit = 50) {
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 14);

  const { data, error } = await supabase
    .from('price_observations')
    .select(`
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
    `)
    .eq('market_id', marketId)
    .gte('price_date', weekAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data;
}

// ── Server-side aggregated supply RPCs (replaces fetching raw rows) ──

export interface SupplySummary {
  total_kg: number;
  daily_avg_kg: number;
  num_days: number;
  oldest_obs: string | null;
  newest_obs: string | null;
}

export async function getMarketSupplySummary(
  marketId: string, days: number, productId?: string | null, provDept?: string | null,
): Promise<SupplySummary | null> {
  const { data, error } = await supabase.rpc('get_market_supply_summary', {
    p_market_id: marketId, p_days: days, p_product_id: productId || null, p_prov_dept: provDept || null,
  });
  if (error) throw error;
  const row = Array.isArray(data) ? data[0] : data;
  if (!row) return null;
  return {
    total_kg: Number(row.total_kg || 0),
    daily_avg_kg: Number(row.daily_avg_kg || 0),
    num_days: Number(row.num_days || 0),
    oldest_obs: row.oldest_obs ?? null,
    newest_obs: row.newest_obs ?? null,
  };
}

export async function getMarketTopProducts(
  marketId: string, days: number, provDept?: string | null, limit = 10,
) {
  const { data, error } = await supabase.rpc('get_market_top_products', {
    p_market_id: marketId, p_days: days, p_prov_dept: provDept || null, p_limit: limit,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    product_id: r.product_id,
    product_name: r.product_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getMarketTopProvenance(
  marketId: string, days: number, productId?: string | null, limit = 15,
) {
  const { data, error } = await supabase.rpc('get_market_top_provenance', {
    p_market_id: marketId, p_days: days, p_product_id: productId || null, p_limit: limit,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    dept_name: r.dept_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getMarketSupply(marketId: string, days = 30) {
  // Paginate — a single market (e.g. Corabastos, Granabastos) can have tens
  // of thousands of supply rows over a year, far above PostgREST's 1000-row
  // response cap. Without paging, time-tile filtering appeared to do
  // nothing because recent data was simply missing from the cached array.
  const PAGE = 1000, MAX = 100000;
  let sinceStr: string | null = null;
  if (days > 0) {
    const since = new Date();
    since.setDate(since.getDate() - days);
    sinceStr = since.toISOString().split('T')[0];
  }
  const all: any[] = [];
  for (let off = 0; off < MAX; off += PAGE) {
    let q = supabase
      .from('supply_observations')
      .select('observation_date, quantity_kg, product_id, provenance_dept_name, provenance_muni_name, dim_product(canonical_name)')
      .eq('market_id', marketId)
      .order('observation_date', { ascending: false })
      .range(off, off + PAGE - 1);
    if (sinceStr) q = q.gte('observation_date', sinceStr);
    const { data, error } = await q;
    if (error) throw error;
    const page = data || [];
    all.push(...page);
    if (page.length < PAGE) break;
  }
  return all;
}

// For each (product, presentation, units), returns the per-market average of
// the latest observation in the window. Server-side — no row-cap bias (the
// old client version paginated 1000 rows at a time and capped at 5K, which
// silently dropped markets for popular products).
export async function getNationalPriceAverages(productIds: string[], days = 30) {
  if (productIds.length === 0) return [];
  const { data, error } = await supabase.rpc('get_national_price_averages', {
    p_product_ids: productIds, p_days: days,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    product_id: r.product_id,
    presentation_id: r.presentation_id,
    units_id: r.units_id,
    avg_price: Math.round(Number(r.avg_price || 0)),
    price_date: r.price_date,
    market_count: Number(r.market_count || 0),
  }));
}

// Returns avg kg per market (across the markets that carry the product) for
// each product. Semantically this is the "typical market volume" baseline
// used by MarketSupplyComparator — preserve that field name (`quantity_kg`)
// for caller compatibility. Server-side GROUP BY, not limited to 10K rows.
export async function getNationalSupplyAverages(productIds: string[], days = 30) {
  if (productIds.length === 0) return [];
  const { data, error } = await supabase.rpc('get_national_supply_averages', {
    p_product_ids: productIds, p_days: days,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    product_id: r.product_id,
    quantity_kg: Number(r.avg_kg_per_market || 0),
    total_kg: Number(r.total_kg || 0),
    market_count: Number(r.market_count || 0),
  }));
}
