/**
 * Product and insumo image handling.
 *
 * Images are stored in the public Supabase `product-images` bucket:
 *   products/{slug}.jpg   — one image per unique product type
 *   insumos/{slug}.jpg    — one image per insumo subgrupo
 *
 * Falls back to category-level Unsplash placeholders when a specific
 * image hasn't been uploaded yet.
 */

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const IMAGE_BUCKET = 'product-images';
const BASE_URL = `${SUPABASE_URL}/storage/v1/object/public/${IMAGE_BUCKET}`;

// -----------------------------------------------------------------------
// Slug helper — mirrors the Python slugify() in fetch_product_images.py
// -----------------------------------------------------------------------

function slugify(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // strip combining diacriticals
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '_')
    .replace(/-+/g, '-')
    .replace(/^[_-]+|[_-]+$/g, '');
}

/**
 * Extract the base product key that maps to an image slug.
 * Mirrors extract_base_product() from the Python script.
 */
function extractBaseProductKey(productName: string, categoryName?: string): string {
  let name = productName
    .replace(/[*+]+$/, '')
    .normalize('NFC')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ');

  if (categoryName === 'Carnes') {
    if (name.includes(',')) {
      name = name.split(',')[0].trim();
    }
    return slugify(name);
  }

  if (name.includes('huevo')) return 'huevo';

  if (categoryName === 'Pescados') {
    let fishName = name.split(',')[0].trim();
    for (const w of ['entero', 'entera', 'fresco', 'fresca', 'congelado',
      'congelada', 'importado', 'importada', 'precocido', 'seco', 'seca']) {
      fishName = fishName.replace(new RegExp(`\\b${w}\\b`, 'g'), '').trim();
    }
    return slugify(fishName);
  }

  // Remove regional qualifiers for produce
  const regional = ['bogotana', 'bogotano', 'pastusa', 'pastuso', 'valluna',
    'valluno', 'huilense', 'antiqueño', 'santandereano', 'regional',
    'importada', 'importado', 'nacional', 'ecuatoriano', 'llanero', 'llanera',
    'aquitania', 'berlín', 'tenerife', 'ocañera', 'peruana'];
  const parts = name.split(/\s+/).filter((p) => !regional.includes(p));
  return slugify(parts.join(' '));
}

// -----------------------------------------------------------------------
// Category-level fallback images (Unsplash)
// -----------------------------------------------------------------------

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
const INSUMO_FALLBACK = 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=200&h=200&fit=crop';

// -----------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------

/**
 * Get product image URL.
 * Tries product-specific image from Supabase first, falls back to category.
 */
export function getProductImageUrl(productName?: string, categoryName?: string): string {
  if (productName) {
    const slug = extractBaseProductKey(productName, categoryName);
    if (slug && slug.length >= 2) {
      return `${BASE_URL}/products/${slug}.jpg`;
    }
  }
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
 * Get insumo image URL.
 * Uses subgrupo-level image from Supabase, falls back to generic.
 */
export function getInsumoImageUrl(insumoName?: string, subgrupo?: string): string {
  if (subgrupo) {
    const slug = slugify(subgrupo);
    if (slug && slug.length >= 2) {
      return `${BASE_URL}/insumos/${slug}.jpg`;
    }
  }
  return INSUMO_FALLBACK;
}

/**
 * Get the fallback image URL if a product image fails to load.
 * Use this as the onError source in Image components.
 */
export function getProductFallbackUrl(categoryName?: string): string {
  if (categoryName && CATEGORY_IMAGES[categoryName]) {
    return CATEGORY_IMAGES[categoryName];
  }
  return DEFAULT_IMAGE;
}

/**
 * Get the fallback image URL for insumos if the subgrupo image fails.
 */
export function getInsumoFallbackUrl(): string {
  return INSUMO_FALLBACK;
}
