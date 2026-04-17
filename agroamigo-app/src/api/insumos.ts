import { supabase } from '../lib/supabase';

export async function getInsumoGrupos() {
  const { data, error } = await supabase
    .from('dim_insumo_grupo')
    .select('id, canonical_name')
    .order('canonical_name');
  if (error) throw error;
  return data;
}

export async function getInsumoSubgrupos(grupoId?: string) {
  let query = supabase
    .from('dim_insumo_subgrupo')
    .select('id, canonical_name, grupo_id')
    .order('canonical_name');
  if (grupoId) query = query.eq('grupo_id', grupoId);
  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function getInsumos(options?: {
  grupoId?: string;
  subgrupoId?: string;
  search?: string;
  limit?: number;
}) {
  const requestedLimit = options?.limit ?? 50;
  const select = 'id, canonical_name, grupo, subgrupo, cpc_code, cpc_id, grupo_id, subgrupo_id';

  let query = supabase
    .from('dim_insumo')
    .select(select)
    .order('canonical_name')
    .limit(requestedLimit);

  if (options?.search) {
    query = query.ilike('canonical_name', `%${options.search}%`);
  }
  if (options?.grupoId) {
    query = query.eq('grupo_id', options.grupoId);
  }
  if (options?.subgrupoId) {
    query = query.eq('subgrupo_id', options.subgrupoId);
  }

  const { data, error } = await query;
  if (error) throw error;
  const results = data || [];

  // Paginate if we hit PostgREST row limit
  if (results.length >= 1000 && requestedLimit > 1000) {
    const pages = Math.ceil(requestedLimit / 1000);
    for (let page = 1; page < pages; page++) {
      let pageQuery = supabase
        .from('dim_insumo')
        .select(select)
        .order('canonical_name')
        .range(page * 1000, Math.min((page + 1) * 1000 - 1, requestedLimit - 1));
      if (options?.search) pageQuery = pageQuery.ilike('canonical_name', `%${options.search}%`);
      if (options?.grupoId) pageQuery = pageQuery.eq('grupo_id', options.grupoId);
      if (options?.subgrupoId) pageQuery = pageQuery.eq('subgrupo_id', options.subgrupoId);
      const { data: pageData, error: pageErr } = await pageQuery;
      if (pageErr) {
        console.error('getInsumos pagination failed at page', page, pageErr);
        break;
      }
      if (!pageData || pageData.length === 0) break;
      results.push(...pageData);
    }
  }

  return results;
}

export async function getInsumoById(id: string) {
  const { data, error } = await supabase
    .from('dim_insumo')
    .select('id, canonical_name, grupo, subgrupo, cpc_code, cpc_id, grupo_id, subgrupo_id')
    .eq('id', id)
    .single();
  if (error) throw error;
  return data;
}

/**
 * Get all CPC codes that have at least one insumo linked.
 * Uses server-side RPC to bypass PostgREST row limits.
 */
export async function getInsumoCpcTree() {
  const { data, error } = await supabase.rpc('get_insumo_cpc_tree');
  if (error) throw error;
  return data || [];
}

export async function getCpcTitle(cpcCode: string) {
  const { data, error } = await supabase
    .from('dim_cpc')
    .select('title')
    .eq('code', cpcCode)
    .single();
  if (error) return '';
  return data?.title || '';
}

export async function getCpcLatestPrices(cpcCode: string) {
  const { data, error } = await supabase.rpc('get_cpc_latest_dept_prices', { p_cpc_code: cpcCode });
  if (error) throw error;
  return data || [];
}

// Same shape as getCpcLatestPrices but scoped to a subgrupo. Used when an
// insumo has no CPC code — the UI falls back to comparing against all
// articles in the same subgrupo.
export async function getSubgrupoLatestPrices(subgrupoId: string) {
  const { data, error } = await supabase.rpc('get_subgrupo_latest_dept_prices', { p_subgrupo_id: subgrupoId });
  if (error) throw error;
  return data || [];
}

export async function getInsumoPricesByDepartment(insumoId: string, limit = 200) {
  const { data, error } = await supabase
    .from('insumo_prices_department')
    .select(`
      price_date, avg_price, department_id, presentation,
      dim_department!inner(id, canonical_name)
    `)
    .eq('insumo_id', insumoId)
    .order('price_date', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data;
}

// One stable row per insumo (latest observation with its presentation).
// Previous client-side version fetched raw rows and kept "most recent per
// insumo_id", which silently picked a random presentation when multiple
// existed — the displayed price then jumped between refreshes. The RPC
// uses DISTINCT ON to return a deterministic single observation per insumo.
export async function getWatchlistInsumoPrices(insumoIds: string[]) {
  if (insumoIds.length === 0) return [];
  const { data, error } = await supabase.rpc('get_watchlist_insumo_latest_prices', {
    p_insumo_ids: insumoIds, p_days: 180,
  });
  if (error) throw error;
  // Match the shape the home screen already expects: dim_department nested.
  return (data || []).map((r: any) => ({
    insumo_id: r.insumo_id,
    price_date: r.price_date,
    avg_price: Number(r.avg_price || 0),
    presentation: r.presentation,
    dim_department: { id: r.department_id, canonical_name: r.dept_name },
  }));
}

export async function getInsumoPricesByMunicipality(insumoId: string, departmentId?: string, limit = 200) {
  let query = supabase
    .from('insumo_prices_municipality')
    .select(`
      price_date, avg_price, department_id, city_id, presentation,
      dim_department!inner(id, canonical_name),
      dim_city(id, canonical_name)
    `)
    .eq('insumo_id', insumoId)
    .order('price_date', { ascending: false })
    .limit(limit);

  if (departmentId) {
    query = query.eq('department_id', departmentId);
  }

  const { data, error } = await query;
  if (error) throw error;
  return data;
}
