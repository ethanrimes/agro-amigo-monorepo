import { getSupabaseClient } from '../lib/supabase';

export async function getComments(entityType: string, entityId: string, limit = 50) {
  const supabase = getSupabaseClient();
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
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('comments')
    .select('id, content, created_at, entity_type, entity_id, user_id, profiles(username)')
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data;
}

export async function createComment(userId: string, entityType: string, entityId: string, content: string) {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('comments')
    .insert({ user_id: userId, entity_type: entityType, entity_id: entityId, content: content.trim() })
    .select('id, content, created_at, user_id, profiles(username)')
    .single();
  if (error) throw error;
  return data;
}
