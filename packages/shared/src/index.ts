// Supabase initialization
export { initSupabase, getSupabaseClient, getSupabaseUrl } from './lib/supabase';

// Session cache
export {
  cacheGet,
  cacheSet,
  cacheDelete,
  cacheInvalidatePrefix,
  cacheClear,
  cachedCall,
  cacheKey,
} from './lib/cache';
export { useCachedQuery } from './lib/useCachedQuery';
export type { UseCachedQueryOptions, UseCachedQueryResult } from './lib/useCachedQuery';

// Formatters
export {
  formatCOP,
  formatCOPCompact,
  formatPctChange,
  formatKg,
  formatDateShort,
  formatDateMedium,
  formatPriceContext,
  pctChange,
} from './lib/format';

// Images
export {
  slugify,
  getProductImageUrl,
  getCategoryImageUrl,
  getInsumoImageUrl,
  getProductFallbackUrl,
  getInsumoFallbackUrl,
} from './lib/images';

// Theme
export { colors } from './theme/colors';
export { spacing, borderRadius, fontSize } from './theme/index';

// API
export * as productsApi from './api/products';
export * as marketsApi from './api/markets';
export * as insumosApi from './api/insumos';
export * as mapApi from './api/map';
export * as supplyApi from './api/supply';
export * as imageAttributionApi from './api/imageAttribution';

// Types
export type * from './types/database';
