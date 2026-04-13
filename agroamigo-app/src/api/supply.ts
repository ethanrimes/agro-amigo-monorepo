import { supabase } from '../lib/supabase';

export async function getProductSupply(productId: string, days = 30) {
  const since = new Date();
  since.setDate(since.getDate() - days);

  const { data, error } = await supabase
    .from('supply_observations')
    .select('observation_date, quantity_kg, city_id, market_id, provenance_dept_name, provenance_muni_name')
    .eq('product_id', productId)
    .gte('observation_date', since.toISOString().split('T')[0])
    .order('observation_date', { ascending: true })
    .limit(500);

  if (error) throw error;
  return data;
}

export async function getSupplyByMarket(marketId: string, days = 30) {
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
