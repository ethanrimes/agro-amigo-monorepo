import { supabase } from '../lib/supabase';

/**
 * Average price per department for a product+presentation (or all products
 * coarsely). Server-side aggregated — no row-cap bias. The presentation is
 * required when a product is given: mixing kg-vs-lb-vs-unit into one "avg"
 * is garbage, so the RPC enforces it and raises if omitted.
 */
export async function getPricesByDepartment(productId?: string, days = 30, presentationId?: string, unitsId?: string) {
  if (productId && (!presentationId || !unitsId)) {
    throw new Error('getPricesByDepartment: presentationId and unitsId are required when productId is provided');
  }
  // The product-required RPC has no nullable OR branch, so the planner always
  // uses idx_price_obs_product_date. The generic signature falls back to the
  // legacy RPC for the (rare) all-products case.
  const { data, error } = productId
    ? await supabase.rpc('get_prices_by_department_for_product', {
        p_product_id: productId,
        p_presentation_id: presentationId,
        p_units_id: unitsId,
        p_days: days,
      })
    : await supabase.rpc('get_prices_by_department', {
        p_product_id: null,
        p_days: days,
        p_presentation_id: null,
        p_units_id: null,
      });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    department_id: r.department_id,
    avg_price: Number(r.avg_price || 0),
    observation_count: Number(r.observation_count || 0),
  }));
}

/**
 * Total supply (kg) per destination department. Server-side GROUP BY —
 * previously the client fetched 10K rows from 19M+ and aggregated in JS,
 * which both timed out and silently skipped most data.
 */
export async function getSupplyByDepartment(productId?: string, days = 30) {
  // Product-required variant sidesteps the generic-plan hedge that made
  // fresa time out (57014). The client never calls this without a product
  // since the cross-product kg sum has no useful meaning.
  const { data, error } = productId
    ? await supabase.rpc('get_supply_by_department_for_product', {
        p_product_id: productId,
        p_days: days,
      })
    : await supabase.rpc('get_supply_by_department', {
        p_product_id: null,
        p_days: days,
      });
  if (error) throw error;
  return (data || []).map((r: any) => ({
    department_id: r.department_id,
    total_kg: Number(r.total_kg || 0),
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
/**
 * Get market IDs that have recent data for a specific product.
 */
export async function getProductPresentationsForMap(productId: string, days = 30) {
  // Server-side DISTINCT. Previously we pulled up to 1000 raw rows with two
  // embedded joins and deduped client-side, which timed out for busy products.
  const { data, error } = await supabase.rpc('get_product_presentations_for_map', {
    p_product_id: productId,
    p_days: days,
  });
  if (error) throw error;
  return ((data || []) as any[]).map(r => {
    const parts = [r.presentation_name, r.units_name].filter(Boolean);
    return { presentation_id: r.presentation_id, units_id: r.units_id, label: parts.join(' \u00b7 ') };
  });
}

export async function getMarketsWithProductData(productId: string, mode: 'price' | 'supply', days = 30, presentationId?: string, unitsId?: string) {
  // Server-side DISTINCT via RPC — returns tens of rows instead of the
  // 5000 raw rows we used to pull down and dedupe client-side.
  if (mode === 'price') {
    const { data, error } = await supabase.rpc('get_price_markets_for_product', {
      p_product_id: productId,
      p_days: days,
      p_presentation_id: presentationId || null,
      p_units_id: unitsId || null,
    });
    if (error) throw error;
    return ((data || []) as any[]).map(r => (typeof r === 'string' ? r : r.get_price_markets_for_product)).filter(Boolean);
  }
  const { data, error } = await supabase.rpc('get_supply_markets_for_product', {
    p_product_id: productId, p_days: days,
  });
  if (error) throw error;
  return ((data || []) as any[]).map(r => (typeof r === 'string' ? r : r.get_supply_markets_for_product)).filter(Boolean);
}

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
