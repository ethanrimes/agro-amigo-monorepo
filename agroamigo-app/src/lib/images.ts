/**
 * Product image handling.
 * In the future, each product/insumo will have an image stored in Supabase storage.
 * For now, we use category-based placeholder images from Unsplash.
 */

const CATEGORY_IMAGES: Record<string, string> = {
  'Frutas': 'https://images.unsplash.com/photo-1619566636858-adf3ef46400b?w=200&h=200&fit=crop',
  'Verduras y hortalizas': 'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=200&h=200&fit=crop',
  'Tubérculos, raíces y plátanos': 'https://images.unsplash.com/photo-1518977676601-b53f82ber63a?w=200&h=200&fit=crop',
  'Carnes': 'https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=200&h=200&fit=crop',
  'Pescados': 'https://images.unsplash.com/photo-1534422298391-e4f8c172dddb?w=200&h=200&fit=crop',
  'Granos y cereales': 'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200&h=200&fit=crop',
  'Procesados': 'https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=200&h=200&fit=crop',
  'Lácteos y huevos': 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=200&h=200&fit=crop',
};

const DEFAULT_IMAGE = 'https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=200&h=200&fit=crop';
const INSUMO_IMAGE = 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=200&h=200&fit=crop';

/**
 * Get product image URL. Later this will check Supabase storage for product-specific images.
 */
export function getProductImageUrl(productName?: string, categoryName?: string): string {
  // TODO: Check Supabase storage for product-specific image
  // const { data } = supabase.storage.from('product-images').getPublicUrl(`${productId}.jpg`);
  if (categoryName && CATEGORY_IMAGES[categoryName]) {
    return CATEGORY_IMAGES[categoryName];
  }
  return DEFAULT_IMAGE;
}

/**
 * Get category image URL for category cards.
 */
export function getCategoryImageUrl(categoryName: string): string {
  return CATEGORY_IMAGES[categoryName] || DEFAULT_IMAGE;
}

/**
 * Get insumo image URL. Later this will check Supabase storage.
 */
export function getInsumoImageUrl(insumoName?: string, subgrupo?: string): string {
  // TODO: Check Supabase storage for insumo-specific image
  return INSUMO_IMAGE;
}
