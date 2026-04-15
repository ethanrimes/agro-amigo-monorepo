import { getSupabaseClient } from '../lib/supabase';

export interface ImageAttribution {
  id: string;
  entity_type: 'product' | 'insumo';
  entity_slug: string;
  storage_path: string;
  source_name: string;
  source_url: string | null;
  source_image_url: string | null;
  license: string | null;
  license_url: string | null;
  author: string | null;
  image_title: string | null;
  fetched_at: string;
}

export async function getImageAttribution(
  entityType: 'product' | 'insumo',
  entitySlug: string,
): Promise<ImageAttribution | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase
    .from('image_attributions')
    .select('*')
    .eq('entity_type', entityType)
    .eq('entity_slug', entitySlug)
    .maybeSingle();

  if (error) {
    console.warn('Error fetching image attribution:', error);
    return null;
  }
  return data;
}
