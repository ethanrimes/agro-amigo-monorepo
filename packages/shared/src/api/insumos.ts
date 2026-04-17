import { getSupabaseClient } from '../lib/supabase';

export async function getInsumoGrupos() {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('dim_insumo_grupo')
    .select('id, canonical_name')
    .order('canonical_name');
  if (error) throw error;
  return data;
}

export async function getInsumoSubgrupos(grupoId?: string) {
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
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

  // If we hit the PostgREST row limit and need more, paginate
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
      if (pageErr) break;
      if (!pageData || pageData.length === 0) break;
      results.push(...pageData);
    }
  }

  return results;
}

export async function getInsumoById(id: string) {
  const supabase = getSupabaseClient();
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
 * Returns the full hierarchy (ancestors included) for building the tree.
 * Uses a server-side RPC to bypass PostgREST row limits.
 */
export async function getInsumoCpcTree() {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_insumo_cpc_tree');
  if (error) throw error;
  return data || [];
}

/**
 * Get the latest price per unique (department, casa_comercial, articulo, presentation)
 * for ALL products sharing a CPC code. Uses server-side RPC.
 */
export async function getCpcTitle(cpcCode: string) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('dim_cpc')
    .select('title')
    .eq('code', cpcCode)
    .single();
  if (error) return '';
  return data?.title || '';
}

export async function getCpcLatestPrices(cpcCode: string) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc('get_cpc_latest_dept_prices', { p_cpc_code: cpcCode });
  if (error) throw error;
  return data || [];
}

export async function getInsumoPricesByDepartment(insumoId: string, limit = 200) {
  const supabase = getSupabaseClient();
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

export async function getWatchlistInsumoPrices(insumoIds: string[]) {
  if (insumoIds.length === 0) return [];
  const supabase = getSupabaseClient();
  const twoWeeksAgo = new Date();
  twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 180);

  const { data, error } = await supabase
    .from('insumo_prices_department')
    .select(`
      insumo_id, price_date, avg_price, presentation,
      dim_department(id, canonical_name)
    `)
    .in('insumo_id', insumoIds)
    .gte('price_date', twoWeeksAgo.toISOString().split('T')[0])
    .order('price_date', { ascending: false })
    .limit(insumoIds.length * 5);

  if (error) throw error;
  return data;
}

export async function getInsumoPricesByMunicipality(insumoId: string, departmentId?: string, limit = 200) {
  const supabase = getSupabaseClient();
  let query = supabase
    .from('insumo_prices_municipality')
    .select(`
      price_date, avg_price, department_id, city_id, presentation,
      dim_department!inner(id, canonical_name)
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
