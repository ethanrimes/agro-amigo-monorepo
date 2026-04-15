import { getSupabaseUrl } from './supabase';

const IMAGE_BUCKET = 'product-images';

function getBaseUrl(): string {
  return `${getSupabaseUrl()}/storage/v1/object/public/${IMAGE_BUCKET}`;
}

export function slugify(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '_')
    .replace(/-+/g, '-')
    .replace(/^[_-]+|[_-]+$/g, '');
}

const CATEGORY_IMAGES: Record<string, string> = {
  'Frutas': 'https://images.unsplash.com/photo-1619566636858-adf3ef46400b?w=200&h=200&fit=crop',
  'Verduras y hortalizas': 'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=200&h=200&fit=crop',
  'Tub\u00e9rculos, ra\u00edces y pl\u00e1tanos': 'https://images.unsplash.com/photo-1518977676601-b53f82ber63a?w=200&h=200&fit=crop',
  'Carnes': 'https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=200&h=200&fit=crop',
  'Pescados': 'https://images.unsplash.com/photo-1534422298391-e4f8c172dddb?w=200&h=200&fit=crop',
  'Granos y cereales': 'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200&h=200&fit=crop',
  'Procesados': 'https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=200&h=200&fit=crop',
  'L\u00e1cteos y huevos': 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=200&h=200&fit=crop',
};

const DEFAULT_IMAGE = 'https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=200&h=200&fit=crop';
const INSUMO_FALLBACK = 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=200&h=200&fit=crop';

export function getProductImageUrl(productName?: string, categoryName?: string): string {
  if (productName) {
    const slug = slugify(productName);
    if (slug && slug.length >= 2) {
      return `${getBaseUrl()}/products/${slug}.jpg`;
    }
  }
  if (categoryName && CATEGORY_IMAGES[categoryName]) {
    return CATEGORY_IMAGES[categoryName];
  }
  return DEFAULT_IMAGE;
}

export function getCategoryImageUrl(categoryName: string): string {
  return CATEGORY_IMAGES[categoryName] || DEFAULT_IMAGE;
}

export function getInsumoImageUrl(insumoName?: string, subgrupo?: string): string {
  if (insumoName) {
    const slug = slugify(insumoName);
    if (slug && slug.length >= 2) {
      return `${getBaseUrl()}/insumos/${slug}.jpg`;
    }
  }
  if (subgrupo) {
    const slug = slugify(subgrupo);
    if (slug && slug.length >= 2) {
      return `${getBaseUrl()}/insumos/${slug}.jpg`;
    }
  }
  return INSUMO_FALLBACK;
}

export function getProductFallbackUrl(categoryName?: string): string {
  if (categoryName && CATEGORY_IMAGES[categoryName]) {
    return CATEGORY_IMAGES[categoryName];
  }
  return DEFAULT_IMAGE;
}

export function getInsumoFallbackUrl(): string {
  return INSUMO_FALLBACK;
}
