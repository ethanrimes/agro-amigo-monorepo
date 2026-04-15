import { createClient, SupabaseClient } from '@supabase/supabase-js';

let _client: SupabaseClient | null = null;
let _url: string = '';

/**
 * Initialize the shared Supabase client.
 * Call this once at app startup (e.g. in a root layout or provider).
 * Pass platform-specific options (e.g. AsyncStorage for React Native).
 */
export function initSupabase(url: string, key: string, options?: Parameters<typeof createClient>[2]): SupabaseClient {
  _url = url;
  _client = createClient(url, key, options);
  return _client;
}

/**
 * Get the initialized Supabase client. Throws if initSupabase hasn't been called.
 */
export function getSupabaseClient(): SupabaseClient {
  if (!_client) {
    throw new Error('Supabase not initialized. Call initSupabase(url, key) first.');
  }
  return _client;
}

/**
 * Get the Supabase project URL (used for storage/image URLs).
 */
export function getSupabaseUrl(): string {
  if (!_url) {
    throw new Error('Supabase not initialized. Call initSupabase(url, key) first.');
  }
  return _url;
}
