import { getSupabaseClient } from '../lib/supabase';

export async function getProductSupply(productId: string, days = 30, marketId?: string) {
  const supabase = getSupabaseClient();

  let query = supabase
    .from('supply_observations')
    .select(`
      observation_date, quantity_kg, city_id, market_id,
      provenance_dept_name, provenance_muni_name,
      dim_market:market_id(canonical_name, dim_city(canonical_name)),
      dim_city:city_id(canonical_name)
    `)
    .eq('product_id', productId)
    .order('observation_date', { ascending: true })
    .limit(1000);

  if (days > 0) {
    const since = new Date();
    since.setDate(since.getDate() - days);
    query = query.gte('observation_date', since.toISOString().split('T')[0]);
  }

  if (marketId) {
    query = query.eq('market_id', marketId);
  }

  const { data, error } = await query;

  if (error) throw error;
  return data;
}

export async function getTopSuppliedProducts(limit = 10) {
  const supabase = getSupabaseClient();
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);

  const { data, error } = await supabase
    .from('supply_observations')
    .select(`product_id, quantity_kg, dim_product!inner(canonical_name)`)
    .gte('observation_date', weekAgo.toISOString().split('T')[0])
    .order('quantity_kg', { ascending: false })
    .limit(500);

  if (error) throw error;

  const map = new Map<string, { product_id: string; name: string; total_kg: number }>();
  for (const row of (data || []) as any[]) {
    const pid = row.product_id;
    const name = row.dim_product?.canonical_name || 'Desconocido';
    const existing = map.get(pid);
    if (existing) {
      existing.total_kg += Number(row.quantity_kg || 0);
    } else {
      map.set(pid, { product_id: pid, name, total_kg: Number(row.quantity_kg || 0) });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_kg - a.total_kg).slice(0, limit);
}

// ── Server-side aggregated supply RPCs ──

export interface SupplySummary {
  total_kg: number;
  daily_avg_kg: number;
  num_days: number;
  oldest_obs: string | null;
  newest_obs: string | null;
}

export async function getProductSupplySummary(
  productId: string, days: number, marketId?: string | null, provDept?: string | null,
): Promise<SupplySummary | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_product_supply_summary', {
    p_product_id: productId, p_days: days, p_market_id: marketId || null, p_prov_dept: provDept || null,
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

export async function getProductTopDestinations(
  productId: string, days: number, provDept?: string | null, limit = 15,
) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_product_top_destinations', {
    p_product_id: productId, p_days: days, p_prov_dept: provDept || null, p_limit: limit,
  });
  if (error) throw error;
  return ((data as any[]) || []).map((r: any) => ({
    market_id: r.market_id,
    market_name: r.market_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getProductTopOrigins(
  productId: string, days: number, marketId?: string | null, limit = 15,
) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_product_top_origins', {
    p_product_id: productId, p_days: days, p_market_id: marketId || null, p_limit: limit,
  });
  if (error) throw error;
  return ((data as any[]) || []).map((r: any) => ({
    dept_name: r.dept_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getProductSupplyByDate(
  productId: string, days: number, marketId?: string | null, provDept?: string | null,
) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_product_supply_by_date', {
    p_product_id: productId, p_days: days, p_market_id: marketId || null, p_prov_dept: provDept || null,
  });
  if (error) throw error;
  return ((data as any[]) || []).map((r: any) => ({ date: r.observation_date, kg: Number(r.total_kg || 0) }));
}

export async function getSupplyByMarket(marketId: string, days = 30) {
  const supabase = getSupabaseClient();
  const since = new Date();
  since.setDate(since.getDate() - days);

  const { data, error } = await supabase
    .from('supply_observations')
    .select(`
      observation_date, quantity_kg, product_id,
      provenance_dept_name, provenance_muni_name,
      dim_product:product_id(canonical_name)
    `)
    .eq('market_id', marketId)
    .gte('observation_date', since.toISOString().split('T')[0])
    .order('observation_date', { ascending: false })
    .limit(500);

  if (error) throw error;
  return data;
}
