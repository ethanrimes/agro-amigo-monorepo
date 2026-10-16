import type { CatalogPage, CatalogPageRequest, UnifiedCatalog } from "./catalog-types";
import { catalogCurrency, catalogMatches, catalogNameMatchesExactly, catalogSavedKey } from "./catalog-display";
import { categoryLabels, departmentLabels } from "./filter-labels";
import { categoryMatches, productCategoryPaths } from "./category-hierarchy";

/** Paginate complete quote identities after applying the same visible filters. */
export function paginateCatalog(catalog: UnifiedCatalog, request: CatalogPageRequest): CatalogPage {
  const saved = request.saved === undefined ? null : new Set(request.saved);
  let matches = catalog.products.filter((product) =>
    (!saved || saved.has(catalogSavedKey(product))) &&
    productCategoryPaths(product).some((path) => categoryMatches(path, request.category || "")) &&
    (!request.currency || catalogCurrency(product) === request.currency) &&
    (!request.q?.trim() || catalogMatches(product, request.q)),
  );
  if (request.q?.trim()) {
    // Keep the existing relevance and card-kind order, then surface newer
    // observations within each bucket. The final source index makes ties
    // deterministic and retains the upstream order for same-day markets.
    const kindPriority = (product: (typeof matches)[number]) =>
      product.kind === "product" ? 0 : 1;
    matches = matches.map((product, sourceIndex) => ({ product, sourceIndex }))
      .sort((a, b) =>
        Number(catalogNameMatchesExactly(b.product, request.q!))
          - Number(catalogNameMatchesExactly(a.product, request.q!)) ||
        kindPriority(a.product) - kindPriority(b.product) ||
        b.product.date.localeCompare(a.product.date) ||
        a.sourceIndex - b.sourceIndex,
      )
      .map(({ product }) => product);
  }
  const offset = Math.max(0, Math.floor(request.offset || 0));
  const limit = Math.min(100, Math.max(1, Math.floor(request.limit || 24)));
  const mapProduct = matches.find((product) => product.map_supported !== false && product.id === "aguacate-hass")
    || matches.find((product) => product.map_supported !== false);
  return {
    ...catalog,
    products: matches.slice(offset, offset + limit),
    total: matches.length,
    regions: departmentLabels(catalog.regions),
    categories: categoryLabels(catalog.products.flatMap(productCategoryPaths)),
    currencies: [...new Set(catalog.products.map(catalogCurrency))].sort(),
    pagination: { offset, limit, has_more: offset + limit < matches.length },
    map_product: mapProduct || null,
  };
}
