import "server-only";
import type { CatalogProduct, UnifiedCatalog } from "../catalog-types";
import type { OfficialPrice } from "../official-types";
import type { Product } from "../market-types";
import { cityCatalogNames } from "./city-catalog-names";
import { cityPublicationEpoch } from "./city-publication-epoch";
import { catalog } from "./queries";
import { latestSummaryReferences } from "./summary-references";
import { latestOfficialReferenceSnapshot } from "./official-references";
import { departmentKey, departmentLabels } from "../filter-labels";
import { normalizeLabel, normalizeOfficialLabels, officialProductSearchNames } from "../label-normalization";
import { officialFrequency, legacyReferencePeriod } from "../catalog-frequency";

const TTL = 5 * 60 * 1000;
const MAX_CACHE_KEYS = 36;
const values = new Map<string, { expires: number; value: unknown }>();
const pending = new Map<string, Promise<unknown>>();

/** Bound both completed entries and concurrent work; failed reads are not cached. */
async function cached<T>(key: string, read: () => Promise<T>, expiresAt?: () => number): Promise<T> {
  const hit = values.get(key);
  if (hit && hit.expires > Date.now()) return hit.value as T;
  const active = pending.get(key);
  if (active) return active as Promise<T>;
  if (pending.size >= MAX_CACHE_KEYS) throw new Error("CATALOG_BUSY");
  const work = read().then((value) => {
    values.delete(key);
    values.set(key, { value, expires: Math.min(Date.now() + TTL, expiresAt?.() ?? Infinity) });
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
    name: normalizeLabel(product.name, "product"),
    category: normalizeLabel(product.category, "category"),
    ...(product.category_paths?.length ? {
      category_paths: product.category_paths.map((path) => path.map((part) => normalizeLabel(part, "category"))),
    } : {}),
    series,
    identity: product.id,
    saved_key: product.id,
    href: `/product/${encodeURIComponent(product.id)}${query.size ? "?" + query : ""}`,
    kind: "product",
    currency: "COP",
    basis,
    market: series === "coffee" ? "Colombia" : region
      ? normalizeLabel(region, "place") : "Colombia · mercados con reporte",
    map_supported: true,
    search_terms: [...new Set([product.name, product.category, ...aliases,
      ...(product.id === "limon-thaiti" ? ["Limón thaití"] : []),
    ])],
  };
}

function officialSelection(quote: OfficialPrice & { previous_price: number | null }): CatalogProduct {
  const identity = "reference:" + quote.quote_key;
  const frequency = officialFrequency(quote.details.period_type, quote.series);
  const display = normalizeOfficialLabels(quote);
  return {
    id: identity,
    identity,
    saved_key: identity,
    href: "/references/" + quote.quote_key,
    kind: "official-reference",
    quote_key: quote.quote_key,
    product_id: quote.product_id,
    name: display.product_name,
    category: normalizeLabel(quote.category, "category"),
    image_key: "produce",
    price: quote.price,
    previous_price: quote.previous_price,
    date: quote.observed_on,
    market_count: 1,
    unit: quote.unit,
    source: quote.publisher,
    // Kept for legacy consumers. Reference cards display their exact basis,
    // rather than interpreting this field as a publisher frequency guarantee.
    period: legacyReferencePeriod(frequency),
    frequency_label: frequency,
    series: quote.series,
    currency: quote.currency,
    basis: quote.basis,
    market: normalizeLabel(quote.market, "place"),
    ...(quote.department ? { department: normalizeLabel(quote.department, "place") } : {}),
    map_supported: false,
    search_terms: [...new Set([
      ...officialProductSearchNames(quote), quote.category, quote.market, quote.publisher,
      quote.basis, quote.unit, ...sourceTerms(Object.fromEntries([
        "source_product", "original_product", "source_description", "variety", "origin",
        "quality", "grade", "presentation", "published_unit", "identity_dimensions",
      ].map((key) => [key, quote.details[key]]))),
    ])],
  };
}

async function allReferencesSnapshot() {
  const rows = await latestOfficialReferenceSnapshot();
  return { value: rows.value.map(officialSelection), expires: rows.expires };
}

async function cityNames(): Promise<Map<string, string[]>> {
  const names = new Map<string, string[]>();
  for (const row of await cityCatalogNames()) {
    names.set(row.product_id, [...(names.get(row.product_id) || []), row.product_name]);
  }
  return names;
}

async function catalogSource<T>(name: string, read: Promise<T>): Promise<T> {
  try { return await read; }
  catch (error) {
    // Operational label only: never emit database URLs, query parameters or keys.
    console.error("Catalog source read failed", name, (error as { code?: string }).code || "unknown");
    throw error;
  }
}

export async function unifiedCatalog(region = "", canonicalOnly = false): Promise<UnifiedCatalog> {
  region = region.slice(0, 100).trim();
  for (let attempt = 0; attempt < 2; attempt++) {
    const epoch = await cityPublicationEpoch();
    let sourceExpiresAt = Infinity;
    const result = await cached<UnifiedCatalog>((canonicalOnly ? "canonical:" : "catalog:") + region + ":" + epoch, async () => {
    const [base, referenceSnapshot, names, summaries] = await Promise.all([
      catalogSource("canonical", catalog(region)),
      canonicalOnly ? Promise.resolve({ value: [], expires: Infinity })
        : catalogSource("official", allReferencesSnapshot()),
      catalogSource("city-aliases", cityNames()),
      canonicalOnly ? Promise.resolve([]) : catalogSource("monthly-summaries", latestSummaryReferences()),
    ]);
    const references = referenceSnapshot.value;
    sourceExpiresAt = Math.min(base.cacheExpiresAt, referenceSnapshot.expires);
    const compatibleReferences = region ? references.filter((quote) => quote.department &&
      departmentKey(quote.department) === departmentKey(region)) : references;
    // The canonical card may summarize a monthly price while the same product
    // has a separately linked, verified market reference. Let a market-qualified
    // product search find that card without changing its price or source link.
    const marketAliases = new Map<string, Set<string>>();
    for (const reference of compatibleReferences) {
      if (!reference.product_id || !names.has(reference.product_id) ||
          !reference.department || !reference.market?.trim()) continue;
      const aliases = marketAliases.get(reference.product_id) || new Set<string>();
      aliases.add(reference.market);
      marketAliases.set(reference.product_id, aliases);
    }
    const canonical = new Map<string, CatalogProduct>();
    for (const product of base.products) {
      if (region && product.id === "cafe-pergamino-seco") continue;
      const summaryNames = summaries.filter((s) => s.canonical_product_id === product.id).map((s) => s.product_name);
      const selection = baseSelection(product, region, [
        ...(names.get(product.id) || []), ...summaryNames, ...(marketAliases.get(product.id) || []),
      ]);
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
    const products = [...canonical.values(), ...compatibleReferences, ...(region ? [] : unmatchedSummaries)];
    const excluded = region ? references.filter((quote) => !quote.department).length + unmatchedSummaries.length + base.products.filter((p) => p.id === "cafe-pergamino-seco").length : 0;
    return {
      products,
      regions: departmentLabels([...base.regions, ...references.flatMap((quote) => quote.department ? [quote.department] : [])]),
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
    }, () => sourceExpiresAt);
    if (epoch === await cityPublicationEpoch()) return result;
  }
  throw new Error("CITY_PUBLICATION_CHANGED_DURING_READ");
}
