import type { CatalogPage, CatalogPageRequest, UnifiedCatalog } from "./catalog-types";
import { catalogCurrency, catalogMatches, catalogSavedKey } from "./catalog-display";

/** Paginate complete quote identities after applying the same visible filters. */
export function paginateCatalog(catalog: UnifiedCatalog, request: CatalogPageRequest): CatalogPage {
  const saved = request.saved === undefined ? null : new Set(request.saved);
  const matches = catalog.products.filter((product) =>
    (!saved || saved.has(catalogSavedKey(product))) &&
    (!request.category || request.category === "Todos" || product.category === request.category) &&
    (!request.currency || catalogCurrency(product) === request.currency) &&
    (!request.q?.trim() || catalogMatches(product, request.q)),
  );
  const offset = Math.max(0, Math.floor(request.offset || 0));
  const limit = Math.min(100, Math.max(1, Math.floor(request.limit || 24)));
  const mapProduct = matches.find((product) => product.map_supported !== false && product.id === "aguacate-hass")
    || matches.find((product) => product.map_supported !== false);
  return {
    ...catalog,
    products: matches.slice(offset, offset + limit),
    total: matches.length,
    categories: [...new Set(catalog.products.map((product) => product.category))].sort((a, b) => a.localeCompare(b, "es")),
    currencies: [...new Set(catalog.products.map(catalogCurrency))].sort(),
    pagination: { offset, limit, has_more: offset + limit < matches.length },
    map_product: mapProduct || null,
  };
}
