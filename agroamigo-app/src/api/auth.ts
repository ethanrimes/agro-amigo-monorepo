import { supabase } from '../lib/supabase';

export async function signUp(email: string, password: string, username: string) {
  // Check username uniqueness first
  const { data: existing } = await supabase
    .from('profiles')
    .select('id')
    .eq('username', username)
    .maybeSingle();
  if (existing) throw new Error('USERNAME_TAKEN');

  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) throw error;
  if (!data.user) throw new Error('SIGNUP_FAILED');

  // Create profile via SECURITY DEFINER function (bypasses RLS for unconfirmed users)
  const { error: profileError } = await supabase
    .rpc('create_user_profile', { p_user_id: data.user.id, p_username: username });
  if (profileError) throw profileError;

  return data;
}

export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function getSession() {
  const { data: { session } } = await supabase.auth.getSession();
  return session;
}

export async function getProfile(userId: string) {
  const { data, error } = await supabase
    .from('profiles')
    .select('id, username, created_at')
    .eq('id', userId)
    .single();
  if (error) throw error;
  return data;
}

export function onAuthStateChange(callback: (event: string, session: any) => void) {
  return supabase.auth.onAuthStateChange(callback);
}
