import { supabase } from '../lib/supabase';

export async function getMarkets() {
  const { data, error } = await supabase
    .from('dim_market')
    .select(`
      id, canonical_name, city_id, sipsa_id,
      dim_city!inner(
        id, canonical_name, department_id,
        dim_department!inner(id, canonical_name)
      ),
      price_observations!inner(market_id)
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

export async function getMarketSupply(marketId: string, days = 30) {
  const since = new Date();
  since.setDate(since.getDate() - days);

  // Get the city_id from the market first
  const { data: market } = await supabase
    .from('dim_market')
    .select('city_id')
    .eq('id', marketId)
    .single();

  if (!market) return [];

  const { data, error } = await supabase
    .from('supply_observations')
    .select('observation_date, quantity_kg, product_id, provenance_dept_name')
    .eq('market_id', marketId)
    .gte('observation_date', since.toISOString().split('T')[0])
    .order('observation_date', { ascending: false })
    .limit(500);

  if (error) throw error;
  return data;
}
