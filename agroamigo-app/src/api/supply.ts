import { supabase } from '../lib/supabase';

// ── Server-side aggregated supply RPCs for product detail ──

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
  const { data, error } = await supabase.rpc('get_product_top_destinations', {
    p_product_id: productId, p_days: days, p_prov_dept: provDept || null, p_limit: limit,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    market_id: r.market_id,
    market_name: r.market_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getProductTopOrigins(
  productId: string, days: number, marketId?: string | null, limit = 15,
) {
  const { data, error } = await supabase.rpc('get_product_top_origins', {
    p_product_id: productId, p_days: days, p_market_id: marketId || null, p_limit: limit,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    dept_name: r.dept_name,
    total_kg: Number(r.total_kg || 0),
    newest_obs: r.newest_obs ?? null,
  }));
}

export async function getProductSupplyByDate(
  productId: string, days: number, marketId?: string | null, provDept?: string | null,
) {
  const { data, error } = await supabase.rpc('get_product_supply_by_date', {
    p_product_id: productId, p_days: days, p_market_id: marketId || null, p_prov_dept: provDept || null,
  });
  if (error) throw error;
  return (data || []).map((r: any) => ({ date: r.observation_date, kg: Number(r.total_kg || 0) }));
}

export async function getTopSuppliedProducts(limit = 10) {
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const { data, error } = await supabase
    .from('supply_observations')
    .select('product_id, quantity_kg, observation_date, dim_product!inner(canonical_name)')
    .gte('observation_date', weekAgo.toISOString().split('T')[0])
    .order('quantity_kg', { ascending: false })
    .limit(500);
  if (error) throw error;
  const map = new Map<string, { product_id: string; name: string; total_kg: number; newest_obs: string | null }>();
  for (const row of (data || []) as any[]) {
    const pid = row.product_id;
    const name = (row.dim_product as any)?.canonical_name || 'Desconocido';
    const existing = map.get(pid);
    if (existing) {
      existing.total_kg += Number(row.quantity_kg || 0);
      if (row.observation_date && (!existing.newest_obs || row.observation_date > existing.newest_obs)) {
        existing.newest_obs = row.observation_date;
      }
    } else {
      map.set(pid, {
        product_id: pid, name,
        total_kg: Number(row.quantity_kg || 0),
        newest_obs: row.observation_date ?? null,
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.total_kg - a.total_kg).slice(0, limit);
}
