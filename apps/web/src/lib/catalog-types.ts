import type { Catalog, Product } from "./market-types";

/** One exact catalog selection; unlike units/bases never share an identity. */
export type CatalogProduct = Product & {
  identity: string;
  saved_key: string;
  href: string;
  kind: "product" | "official-reference";
  currency: string;
  basis: string;
  market: string;
  map_supported: boolean;
  search_terms: string[];
  product_id?: string;
  quote_key?: string;
};

export type UnifiedCatalog = Omit<Catalog, "products"> & {
  products: CatalogProduct[];
  filters: {
    region: string;
    reference_scope: "all" | "regional-only";
    excluded_nonregional_count: number;
    excluded_nonregional_reason: string | null;
  };
};

export type CatalogPageRequest = {
  region?: string;
  q?: string;
  category?: string;
  currency?: string;
  offset?: number;
  limit?: number;
  saved?: string[];
};

export type CatalogPage = UnifiedCatalog & {
  total: number;
  categories: string[];
  currencies: string[];
  pagination: { offset: number; limit: number; has_more: boolean };
  map_product: CatalogProduct | null;
};
