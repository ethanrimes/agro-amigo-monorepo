import { getSupabaseClient } from '../lib/supabase';

export async function getMarkets() {
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 180);

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
  const supabase = getSupabaseClient();
  const since = new Date();
  since.setDate(since.getDate() - days);

  const { data: market } = await supabase
    .from('dim_market')
    .select('city_id')
    .eq('id', marketId)
    .single();

  if (!market) return [];

  const { data, error } = await supabase
    .from('supply_observations')
    .select('observation_date, quantity_kg, product_id, provenance_dept_name, dim_product!inner(canonical_name)')
    .eq('market_id', marketId)
    .gte('observation_date', since.toISOString().split('T')[0])
    .order('observation_date', { ascending: false })
    .limit(500);

  if (error) throw error;
  return data;
}

export async function getNationalPriceAverages(productIds: string[]) {
  if (productIds.length === 0) return [];
  const supabase = getSupabaseClient();
  const since = new Date();
  since.setDate(since.getDate() - 30);

  const allData: any[] = [];
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from('price_observations')
      .select('product_id, avg_price, min_price, max_price, price_date, presentation_id, units_id, market_id')
      .in('product_id', productIds)
      .gte('price_date', since.toISOString().split('T')[0])
      .order('price_date', { ascending: false })
      .range(offset, offset + 999);
    if (error) throw error;
    allData.push(...(data || []));
    if (!data || data.length < 1000) break;
    offset += 1000;
    if (offset >= 5000) break;
  }

  const latestPerMarket = new Map<string, any>();
  for (const row of allData) {
    const k = `${row.product_id}|${row.presentation_id}|${row.units_id}|${row.market_id}`;
    if (!latestPerMarket.has(k) || row.price_date > latestPerMarket.get(k).price_date) {
      latestPerMarket.set(k, row);
    }
  }

  const groups = new Map<string, any[]>();
  for (const row of latestPerMarket.values()) {
    const k = `${row.product_id}|${row.presentation_id}|${row.units_id}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(row);
  }

  return Array.from(groups.values()).map(rows => {
    const prices = rows.map((r: any) => r.avg_price ?? ((r.min_price + r.max_price) / 2));
    const avgPrice = prices.reduce((s: number, v: number) => s + v, 0) / prices.length;
    const latestDate = rows.reduce((max: string, r: any) => r.price_date > max ? r.price_date : max, rows[0].price_date);
    return {
      product_id: rows[0].product_id,
      presentation_id: rows[0].presentation_id,
      units_id: rows[0].units_id,
      avg_price: Math.round(avgPrice),
      price_date: latestDate,
      market_count: rows.length,
    };
  });
}

export async function getNationalSupplyAverages(productIds: string[], days = 30) {
  if (productIds.length === 0) return [];
  const supabase = getSupabaseClient();
  const since = new Date();
  since.setDate(since.getDate() - days);

  const allData: any[] = [];
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from('supply_observations')
      .select('product_id, quantity_kg, market_id')
      .in('product_id', productIds)
      .gte('observation_date', since.toISOString().split('T')[0])
      .range(offset, offset + 999);
    if (error) throw error;
    allData.push(...(data || []));
    if (!data || data.length < 1000) break;
    offset += 1000;
    if (offset >= 10000) break;
  }

  const productMarkets = new Map<string, Map<string, number>>();
  for (const row of allData) {
    if (!productMarkets.has(row.product_id)) productMarkets.set(row.product_id, new Map());
    const mmap = productMarkets.get(row.product_id)!;
    mmap.set(row.market_id, (mmap.get(row.market_id) || 0) + (row.quantity_kg || 0));
  }

  return Array.from(productMarkets.entries()).map(([product_id, mmap]) => ({
    product_id,
    quantity_kg: Array.from(mmap.values()).reduce((s, v) => s + v, 0) / mmap.size,
    market_count: mmap.size,
  }));
}
