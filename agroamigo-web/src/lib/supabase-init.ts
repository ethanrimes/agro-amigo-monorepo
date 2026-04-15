import { initSupabase } from '@agroamigo/shared';

// Initialize the shared Supabase client for the web app.
// This module is imported once from the Providers component (side-effect import).
const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const key = process.env.NEXT_PUBLIC_SUPABASE_KEY!;

initSupabase(url, key);
