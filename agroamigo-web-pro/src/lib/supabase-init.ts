import { initSupabase } from '@agroamigo/shared';

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const key = process.env.NEXT_PUBLIC_SUPABASE_KEY!;

initSupabase(url, key);
