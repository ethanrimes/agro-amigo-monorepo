import { supabase } from '../lib/supabase';

export async function getComments(entityType: string, entityId: string, limit = 50) {
  const { data, error } = await supabase
    .from('comments')
    .select('id, content, created_at, user_id, profiles(username)')
    .eq('entity_type', entityType)
    .eq('entity_id', entityId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data;
}

export async function getLatestComments(limit = 20) {
  const { data: rows, error } = await supabase
    .from('comments')
    .select('id, content, created_at, entity_type, entity_id, user_id, profiles(username)')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  if (!rows || rows.length === 0) return [];

  const ENTITY_TABLES = { product: 'dim_product', market: 'dim_market', insumo: 'dim_insumo' } as const;
  const idsByType: Record<keyof typeof ENTITY_TABLES, Set<string>> = {
    product: new Set(), market: new Set(), insumo: new Set(),
  };
  for (const r of rows) {
    const t = r.entity_type as keyof typeof ENTITY_TABLES;
    if (t in idsByType && r.entity_id) idsByType[t].add(r.entity_id);
  }

  const nameMap = new Map<string, string>();
  await Promise.all((Object.keys(ENTITY_TABLES) as Array<keyof typeof ENTITY_TABLES>).map(async (t) => {
    const ids = Array.from(idsByType[t]);
    if (ids.length === 0) return;
    const { data } = await supabase.from(ENTITY_TABLES[t]).select('id, canonical_name').in('id', ids);
    for (const d of data || []) nameMap.set(`${t}:${d.id}`, d.canonical_name);
  }));

  return rows.map(r => ({ ...r, entity_name: nameMap.get(`${r.entity_type}:${r.entity_id}`) || '' }));
}

export async function createComment(userId: string, entityType: string, entityId: string, content: string) {
  const { data, error } = await supabase
    .from('comments')
    .insert({ user_id: userId, entity_type: entityType, entity_id: entityId, content: content.trim() })
    .select('id, content, created_at, user_id, profiles(username)')
    .single();
  if (error) throw error;
  return data;
}
