import { supabase } from '../lib/supabase';

/**
 * Get average price per department for a given product (or all products).
 * Used for the Price mode choropleth.
 */
export async function getPricesByDepartment(productId?: string, days = 30) {
  const since = new Date();
  since.setDate(since.getDate() - days);

  let query = supabase
    .from('price_observations')
    .select('department_id, min_price, max_price, avg_price')
    .gte('price_date', since.toISOString().split('T')[0]);

  if (productId) {
    query = query.eq('product_id', productId);
  }

  const { data, error } = await query.limit(5000);
  if (error) throw error;

  // Aggregate by department
  const deptMap = new Map<string, { sum: number; count: number }>();
  for (const row of data || []) {
    const price = row.avg_price ?? row.max_price ?? row.min_price ?? 0;
    if (price === 0) continue;
    const existing = deptMap.get(row.department_id);
    if (existing) {
      existing.sum += price;
      existing.count += 1;
    } else {
      deptMap.set(row.department_id, { sum: price, count: 1 });
    }
  }

  return Array.from(deptMap.entries()).map(([deptId, { sum, count }]) => ({
    department_id: deptId,
    avg_price: sum / count,
    observation_count: count,
  }));
}

/**
 * Get total supply (kg) per department for a given product (or all products).
 * Used for the Supply mode choropleth.
 */
export async function getSupplyByDepartment(productId?: string, days = 30) {
  const since = new Date();
  since.setDate(since.getDate() - days);

  let query = supabase
    .from('supply_observations')
    .select('city_id, quantity_kg')
    .gte('observation_date', since.toISOString().split('T')[0]);

  if (productId) {
    query = query.eq('product_id', productId);
  }

  const { data, error } = await query.limit(10000);
  if (error) throw error;

  // We need city -> department mapping. Get it from dim_city.
  const cityIds = [...new Set((data || []).map(r => r.city_id))];
  if (cityIds.length === 0) return [];

  const { data: cities } = await supabase
    .from('dim_city')
    .select('id, department_id')
    .in('id', cityIds);

  const cityToDept = new Map<string, string>();
  for (const c of cities || []) {
    cityToDept.set(c.id, c.department_id);
  }

  // Aggregate by department
  const deptMap = new Map<string, number>();
  for (const row of data || []) {
    const deptId = cityToDept.get(row.city_id);
    if (!deptId) continue;
    deptMap.set(deptId, (deptMap.get(deptId) || 0) + (row.quantity_kg || 0));
  }

  return Array.from(deptMap.entries()).map(([deptId, totalKg]) => ({
    department_id: deptId,
    total_kg: totalKg,
  }));
}

/**
 * Get department dimension data with DIVIPOLA codes.
 */
export async function getDepartments() {
  const { data, error } = await supabase
    .from('dim_department')
    .select('id, canonical_name, divipola_code')
    .order('canonical_name');
  if (error) throw error;
  return data;
}

/**
 * Get market locations by joining market -> city -> divipola_municipios for lat/lng.
 */
export async function getMarketLocations() {
  const { data: markets, error: mErr } = await supabase
    .from('dim_market')
    .select(`
      id, canonical_name, sipsa_id,
      dim_city!inner(
        id, canonical_name, divipola_code, department_id,
        dim_department!inner(id, canonical_name, divipola_code)
      )
    `);
  if (mErr) throw mErr;

  // Get lat/lng from divipola_municipios
  const divCodes = (markets || [])
    .map((m: any) => m.dim_city?.divipola_code)
    .filter(Boolean);

  if (divCodes.length === 0) return (markets || []).map((m: any) => ({ ...m, lat: null, lng: null }));

  const { data: municipios } = await supabase
    .from('divipola_municipios')
    .select('codigo_municipio, latitud, longitud')
    .in('codigo_municipio', divCodes);

  const coordMap = new Map<string, { lat: number; lng: number }>();
  for (const m of municipios || []) {
    if (m.latitud && m.longitud) {
      coordMap.set(m.codigo_municipio, { lat: m.latitud, lng: m.longitud });
    }
  }

  return (markets || []).map((m: any) => {
    const code = m.dim_city?.divipola_code;
    const coords = code ? coordMap.get(code) : null;
    return {
      id: m.id,
      name: m.canonical_name,
      city: m.dim_city?.canonical_name,
      department: m.dim_city?.dim_department?.canonical_name,
      dept_divipola: m.dim_city?.dim_department?.divipola_code,
      lat: coords?.lat ?? null,
      lng: coords?.lng ?? null,
    };
  });
}
