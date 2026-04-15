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
  let query = supabase
    .from('dim_insumo')
    .select('id, canonical_name, grupo, subgrupo, cpc_code, grupo_id, subgrupo_id')
    .order('canonical_name')
    .limit(options?.limit ?? 50);

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
  return data;
}

export async function getInsumoById(id: string) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('dim_insumo')
    .select('id, canonical_name, grupo, subgrupo, cpc_code, grupo_id, subgrupo_id')
    .eq('id', id)
    .single();
  if (error) throw error;
  return data;
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
