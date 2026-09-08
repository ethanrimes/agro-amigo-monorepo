import type { CatalogProduct } from "./catalog-types";
import type { Product } from "./market-types";
import { unitLabel } from "./market-types";
import { fold } from "./planning-math";

/** Older home-page rows and unified catalog rows share the same card. */
export type CatalogCard = Product & Partial<CatalogProduct>;

export const catalogIdentity = (product: CatalogCard) =>
  product.identity ||
  [
    product.id,
    product.unit,
    product.source,
    product.presentation || "",
    product.units || "",
  ].join(":");

export const catalogSavedKey = (product: CatalogCard) =>
  product.saved_key || product.id;

export const catalogCurrency = (product: CatalogCard) =>
  product.currency || "COP";

const productSearchAliases: Record<string, string> = {
  rosa: "rosa",
  rosas: "rosa",
  rose: "rosa",
  roses: "rosa",
  arabica: "arabica",
  arabicas: "arabica",
  arabico: "arabica",
  arabicos: "arabica",
  arabigo: "arabica",
  arabigos: "arabica",
};

export function catalogMatches(product: CatalogCard, query: string) {
  const text = fold(
    [
      product.name,
      product.presentation,
      product.units,
      ...(product.search_terms || []),
    ]
      .filter(Boolean)
      .join(" "),
  );
  const words = new Set(
    text.split(/[^a-z0-9]+/).map((word) => productSearchAliases[word] || word),
  );
  return fold(query)
    .split(/\s+/)
    .every((word) =>
      productSearchAliases[word]
        ? words.has(productSearchAliases[word])
        : text.includes(word),
    );
}

export function catalogHref(product: CatalogCard, returnTo?: string) {
  const params = new URLSearchParams();
  if (product.series) {
    params.set("series", product.series);
    params.set("presentation", product.presentation || "");
    params.set("units", product.units || "");
  }
  const href =
    product.href || `/product/${product.id}${params.size ? "?" + params : ""}`;
  if (!returnTo) return href;
  const url = new URL(href, "https://agroamigo.invalid");
  url.searchParams.set("returnTo", returnTo);
  return url.pathname + url.search + url.hash;
}

export function catalogReturnTo(
  path: string,
  query: string,
  category: string,
  currency: string,
) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (category && category !== "Todos") params.set("category", category);
  if (currency) params.set("currency", currency);
  return path + (params.size ? "?" + params : "");
}

export function catalogPriceNumber(product: CatalogCard) {
  return new Intl.NumberFormat("es-CO", {
    maximumFractionDigits:
      catalogCurrency(product) === "COP"
        ? product.kind === "official-reference"
          ? 2
          : 0
        : 4,
  }).format(product.price);
}

export const catalogUnit = (product: CatalogCard) => unitLabel(product.unit);

export const catalogBasis = (product: CatalogCard) =>
  product.basis ||
  (product.id === "cafe-pergamino-seco"
    ? "Referencia nacional del café"
    : product.series === "city"
      ? "Precio mayorista por empaque"
      : product.series === "farmgate"
        ? "Precio de leche en finca"
        : product.series === "mill"
          ? "Precio de arroz en molino"
          : product.period === "monthly"
            ? "Promedio mayorista mensual"
            : "Precio publicado");

export const catalogDate = (date: string) =>
  new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "America/Bogota",
  }).format(new Date(date.slice(0, 10) + "T12:00:00Z"));
