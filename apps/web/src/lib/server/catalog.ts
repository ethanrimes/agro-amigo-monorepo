import "server-only";
import type { CatalogProduct, UnifiedCatalog } from "../catalog-types";
import type { OfficialPrice } from "../official-types";
import type { Product } from "../market-types";
import { database } from "./db";
import { catalog } from "./queries";
import { latestSummaryReferences } from "./summary-references";

const TTL = 5 * 60 * 1000;
const MAX_CACHE_KEYS = 36;
const values = new Map<string, { expires: number; value: unknown }>();
const pending = new Map<string, Promise<unknown>>();

/** Bound both completed entries and concurrent work; failed reads are not cached. */
async function cached<T>(key: string, read: () => Promise<T>): Promise<T> {
  const hit = values.get(key);
  if (hit && hit.expires > Date.now()) return hit.value as T;
  const active = pending.get(key);
  if (active) return active as Promise<T>;
  if (pending.size >= MAX_CACHE_KEYS) throw new Error("CATALOG_BUSY");
  const work = read().then((value) => {
    values.delete(key);
    values.set(key, { value, expires: Date.now() + TTL });
    while (values.size > MAX_CACHE_KEYS) values.delete(values.keys().next().value!);
    return value;
  }).finally(() => pending.delete(key));
  pending.set(key, work);
  return work;
}

function sourceTerms(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(sourceTerms);
  if (value && typeof value === "object") return Object.values(value).flatMap(sourceTerms);
  return [];
}

function baseSelection(product: Product, region: string, aliases: string[]): CatalogProduct {
  const series = product.series || (product.id === "cafe-pergamino-seco" ? "coffee" : "monthly");
  const query = new URLSearchParams();
  if (series !== "coffee") {
    query.set("series", series);
    query.set("presentation", product.presentation!);
    query.set("units", product.units!);
    if (series === "city") query.set("history", "all");
  }
  query.set("region", region);
  const basis = {
    coffee: "Referencia nacional FNC",
    city: "Precio mayorista por empaque",
    monthly: "Promedio mensual mayorista",
    farmgate: "Leche cruda en finca",
    mill: "Precio en molino",
  }[series] || product.source;
  return {
    ...product,
    series,
    identity: product.id,
    saved_key: product.id,
    href: `/product/${encodeURIComponent(product.id)}${query.size ? "?" + query : ""}`,
    kind: "product",
    currency: "COP",
    basis,
    market: series === "coffee" ? "Colombia" : region || "Colombia · mercados con reporte",
    map_supported: true,
    search_terms: [...new Set([product.name, product.category, ...aliases])],
  };
}

function officialSelection(quote: OfficialPrice & { previous_price: number | null }): CatalogProduct {
  const identity = "reference:" + quote.quote_key;
  return {
    id: identity,
    identity,
    saved_key: identity,
    href: "/references/" + quote.quote_key,
    kind: "official-reference",
    quote_key: quote.quote_key,
    product_id: quote.product_id,
    name: quote.product_name,
    category: quote.category,
    image_key: "produce",
    price: quote.price,
    previous_price: quote.previous_price,
    date: quote.observed_on,
    market_count: 1,
    unit: quote.unit,
    source: quote.publisher,
    // Kept for legacy consumers. Reference cards display their exact basis,
    // rather than interpreting this field as a publisher frequency guarantee.
    period: quote.series.includes("monthly") ? "monthly" : "daily",
    series: quote.series,
    currency: quote.currency,
    basis: quote.basis,
    market: quote.market,
    map_supported: false,
    search_terms: [...new Set([
      quote.product_name, quote.category, quote.market, quote.publisher,
      quote.basis, quote.unit, ...sourceTerms(Object.fromEntries([
        "source_product", "original_product", "source_description", "variety", "origin",
        "quality", "grade", "presentation", "published_unit", "identity_dimensions",
      ].map((key) => [key, quote.details[key]]))),
    ])],
  };
}

async function allReferences(): Promise<CatalogProduct[]> {
  return cached("official", async () => {
    const { rows } = await database().query<OfficialPrice & { previous_price: number | null }>(`
      SELECT DISTINCT ON(quote_key) quote_key,product_id,product_name,category,
        publisher,series,basis,currency,unit,market,observed_on,price,details,
        lead(price) OVER(PARTITION BY quote_key ORDER BY observed_on DESC) AS previous_price
      FROM published_official_price
      WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY quote_key,observed_on DESC
    `);
    return rows.map(officialSelection);
  });
}

async function cityNames(): Promise<Map<string, string[]>> {
  return cached("city-names", async () => {
    const { rows } = await database().query<{ product_id: string; names: string[] }>(`
      SELECT product_id,array_agg(DISTINCT product_name ORDER BY product_name) AS names
      FROM regional_price WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      GROUP BY product_id
    `);
    return new Map(rows.map((r) => [r.product_id, r.names]));
  });
}

export async function unifiedCatalog(region = ""): Promise<UnifiedCatalog> {
  region = region.slice(0, 100).trim();
  return cached("catalog:" + region, async () => {
    const [base, references, names, summaries] = await Promise.all([
      catalog(region), allReferences(), cityNames(), latestSummaryReferences(),
    ]);
    const canonical = new Map<string, CatalogProduct>();
    for (const product of base.products) {
      if (region && product.id === "cafe-pergamino-seco") continue;
      const summaryNames = summaries.filter((s) => s.canonical_product_id === product.id).map((s) => s.product_name);
      const selection = baseSelection(product, region, [...(names.get(product.id) || []), ...summaryNames]);
      const old = canonical.get(product.id);
      // One canonical card. Select one compatible quote, never average units or
      // price bases together merely because the product identifier is shared.
      if (!old || selection.date > old.date ||
          (selection.date === old.date && selection.market_count > old.market_count) ||
          (selection.date === old.date && selection.market_count === old.market_count && selection.unit < old.unit)) {
        canonical.set(product.id, selection);
      }
    }
    const unmatchedSummaries = summaries.filter((s) => !s.canonical_product_id || !canonical.has(s.canonical_product_id))
      .map((s) => officialSelection({ ...s, previous_price: null }));
    const products = [...canonical.values(), ...(region ? [] : [...references, ...unmatchedSummaries])];
    const excluded = region ? references.length + unmatchedSummaries.length + base.products.filter((p) => p.id === "cafe-pergamino-seco").length : 0;
    return {
      products,
      regions: base.regions,
      latestDate: products.reduce<string | null>((day, p) => !day || p.date > day ? p.date : day, null),
      filters: {
        region,
        reference_scope: region ? "regional-only" : "all",
        excluded_nonregional_count: excluded,
        excluded_nonregional_reason: excluded
          ? "Quita el filtro de departamento para consultar las referencias sin departamento verificado."
          : null,
      },
    };
  });
}
