import { createHash } from "node:crypto";
import type { OfficialPrice } from "../official-types";

// Unicode 16 case-fold mappings whose Python 3.14 casefold differs from
// default lowercase; keeps JS identity matching aligned with NFC.casefold.
const CASEFOLD_DELTAS: Readonly<Record<string, string>> =
  require("./unicode-casefold-deltas.json");

export type WeeklyIdentityRow = OfficialPrice & { previous_price?: number | null };

export type CapitalizationGroup = {
  canonicalKey: string;
  canonicalName: string;
  keys: string[];
  variants: string[];
  cards: WeeklyIdentityRow[];
};

export const MAX_WEEKLY_CAPITALIZATION_KEYS = 8;

const SOURCE_PRODUCT = "source_product";
const IDENTITY_FIELDS = ["product_id", "publisher", "series", "basis", "currency", "unit", "market"] as const;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[a-f0-9]{64}$/;

export function isWeeklyCapitalizationConflict(error: unknown): boolean {
  return error instanceof Error && /^WEEKLY_CAPITALIZATION_(IDENTITY|PRICE|PERIOD)_CONFLICT$/.test(error.message);
}

// Python's official quote-key identity uses json.dumps(sort_keys=True,
// ensure_ascii=False), including spaces after commas and colons.
function pythonJson(value: unknown): string {
  if (typeof value === "string") return JSON.stringify(value);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) =>
      `${pythonJson(key)}: ${pythonJson(object[key])}`).join(", ")}}`;
  }
  return JSON.stringify(value);
}

function productSlug(value: string): string {
  return value.normalize("NFKD").replace(/[^\x00-\x7F]/gu, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function isDate(value: unknown): value is string {
  if (typeof value !== "string" || !DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

// NFC + Unicode case-insensitive comparison only. Accents and punctuation
// remain code points in the comparison; no NFKD, accent stripping, whitespace
// rewriting, or product-label alias table is used.
export function nfcCaseFold(value: string): string {
  const normalized = value.normalize("NFC");
  let folded = "";
  for (const character of normalized) {
    folded += CASEFOLD_DELTAS[character.codePointAt(0)!.toString(16)] ??
      character.toLowerCase();
  }
  return folded.normalize("NFC");
}

function sourceProduct(row: WeeklyIdentityRow): string | null {
  const dimensions = row.details?.identity_dimensions;
  if (!dimensions || typeof dimensions !== "object" || Array.isArray(dimensions)) return null;
  const keys = Object.keys(dimensions);
  if (keys.length !== 1 || keys[0] !== SOURCE_PRODUCT) return null;
  const value = (dimensions as Record<string, unknown>)[SOURCE_PRODUCT];
  return typeof value === "string" && value.length > 0 && row.product_name === value ? value : null;
}

/** Reconstruct the retained key using its own literal identity dimensions. */
export function expectedWeeklyQuoteKey(row: WeeklyIdentityRow): string | null {
  const literal = sourceProduct(row);
  if (!literal || !row.product_id || productSlug(row.product_name) !== row.product_id ||
      row.publisher !== "DANE · SIPSA" || row.series !== "dane-weekly" ||
      row.basis !== "Precio mayorista semanal" || !row.currency || !row.unit || !row.market ||
      row.details?.period_type !== "weekly" || row.details?.price_statistic !== "published_mean") return null;
  const identity = {
    product_id: row.product_id,
    series: row.series,
    market: row.market,
    currency: row.currency,
    unit: row.unit,
    basis: row.basis,
    dimensions: { source_product: literal },
  };
  return createHash("sha256").update(pythonJson(identity), "utf8").digest("hex");
}

function validateRow(row: WeeklyIdentityRow): string {
  const literal = sourceProduct(row);
  if (!literal || expectedWeeklyQuoteKey(row) !== row.quote_key ||
      row.details?.period_type !== "weekly" || row.details?.price_statistic !== "published_mean" ||
      !isDate(row.observed_on) || !isDate(row.period_start) ||
      row.details?.period_end !== row.observed_on || row.period_start > row.observed_on ||
      !Number.isFinite(row.price) || row.price <= 0 ||
      (row.min_price !== null && (!Number.isFinite(row.min_price) || row.min_price <= 0)) ||
      (row.max_price !== null && (!Number.isFinite(row.max_price) || row.max_price <= 0)) ||
      (row.min_price !== null && row.min_price > row.price) ||
      (row.max_price !== null && row.price > row.max_price) ||
      typeof row.document_id !== "string" || !SHA256.test(row.document_id) ||
      typeof row.source_locator !== "string" || !row.source_locator ||
      typeof row.source_url !== "string" || !row.source_url.startsWith("https://www.dane.gov.co/files/"))
    throw new Error("WEEKLY_CAPITALIZATION_IDENTITY_CONFLICT");
  return literal;
}

function signature(row: WeeklyIdentityRow, literal: string): string {
  return JSON.stringify([
    ...IDENTITY_FIELDS.map((field) => row[field]),
    nfcCaseFold(literal),
  ]);
}

/** Groups authentic weekly quote keys that differ only in source-product case. */
export function capitalizationWeeklyGroups(cards: WeeklyIdentityRow[]): {
  groups: CapitalizationGroup[];
  byKey: Map<string, CapitalizationGroup>;
} {
  const buckets = new Map<string, { rows: WeeklyIdentityRow[]; invalid: boolean }>();
  for (const row of cards) {
    const literal = sourceProduct(row);
    if (!literal || row.publisher !== "DANE · SIPSA" || row.series !== "dane-weekly" ||
        row.basis !== "Precio mayorista semanal" || !row.currency || !row.unit || !row.market) continue;
    const id = signature(row, literal);
    const bucket = buckets.get(id) || { rows: [], invalid: false };
    bucket.rows.push(row);
    if (expectedWeeklyQuoteKey(row) !== row.quote_key) bucket.invalid = true;
    buckets.set(id, bucket);
  }

  const groups: CapitalizationGroup[] = [];
  const byKey = new Map<string, CapitalizationGroup>();
  for (const bucket of buckets.values()) {
    const keys = [...new Set(bucket.rows.map((row) => row.quote_key))];
    const variants = [...new Set(bucket.rows.map((row) => sourceProduct(row)!))];
    if (bucket.invalid || keys.length < 2 || keys.length > MAX_WEEKLY_CAPITALIZATION_KEYS || variants.length < 2 ||
        variants.some((value) => nfcCaseFold(value) !== nfcCaseFold(variants[0]))) continue;
    try { bucket.rows.forEach(validateRow); } catch { continue; }
    const latestDate = bucket.rows.reduce((latest, row) => row.observed_on > latest ? row.observed_on : latest, "");
    const newest = bucket.rows.filter((row) => row.observed_on === latestDate);
    const canonical = [...newest].sort((a, b) => {
      const upperCount = (value: string) => [...value].filter((char) => char !== char.toLowerCase()).length;
      return upperCount(a.product_name) - upperCount(b.product_name) ||
        a.product_name.localeCompare(b.product_name) || a.quote_key.localeCompare(b.quote_key);
    })[0];
    const group: CapitalizationGroup = {
      canonicalKey: canonical.quote_key,
      canonicalName: canonical.product_name,
      keys,
      variants,
      cards: bucket.rows,
    };
    groups.push(group);
    for (const key of keys) byKey.set(key, group);
  }
  return { groups, byKey };
}

function evidence(row: WeeklyIdentityRow) {
  return {
    original_quote_key: row.quote_key,
    original_product_id: row.product_id,
    original_product_name: row.product_name,
    source_product_literal: sourceProduct(row),
    original_category: row.category,
    publisher: row.publisher,
    series: row.series,
    basis: row.basis,
    currency: row.currency,
    unit: row.unit,
    market: row.market,
    observed_on: row.observed_on,
    period_start: row.period_start,
    price: row.price,
    min_price: row.min_price,
    max_price: row.max_price,
    document_id: row.document_id,
    source_url: row.source_url,
    source_locator: row.source_locator,
    source_page: row.source_page ?? null,
    original_details: row.details,
  };
}

/** Collapse the grouped identity to one latest card, preserving raw witnesses. */
export function collapseCapitalizationWeeklyCatalog<T extends WeeklyIdentityRow>(
  cards: T[], groups: CapitalizationGroup[],
): T[] {
  const groupedKeys = new Set(groups.flatMap((group) => group.keys));
  const output = cards.filter((card) => !groupedKeys.has(card.quote_key));
  for (const group of groups) {
    const latestDate = group.cards.reduce((latest, row) =>
      row.observed_on > latest ? row.observed_on : latest, "");
    const newest = group.cards.filter((row) => row.observed_on === latestDate);
    const first = newest[0];
    if (!first || newest.some((row) => row.period_start !== first.period_start ||
        row.details?.period_end !== first.details?.period_end))
      throw new Error("WEEKLY_CAPITALIZATION_PERIOD_CONFLICT");
    if (newest.some((row) => row.price !== first.price || row.min_price !== first.min_price ||
        row.max_price !== first.max_price))
      throw new Error("WEEKLY_CAPITALIZATION_PRICE_CONFLICT");
    const primary = newest.find((row) => row.quote_key === group.canonicalKey) || newest[0];
    output.push({
      ...primary,
      quote_key: group.canonicalKey,
      product_name: group.canonicalName,
      details: {
        ...primary.details,
        original_quote_key: primary.quote_key,
        original_product_name: primary.product_name,
        source_product_literal: sourceProduct(primary),
        capitalization_identity_sources: group.cards.map(evidence),
        ...(newest.length > 1 ? { capitalization_equivalence_sources: newest.map(evidence) } : {}),
      },
    } as unknown as T);
  }
  return output;
}

/** Union disjoint histories; retain every equal-value witness and reject conflicts. */
export function mergeCapitalizationWeeklyHistory(
  group: CapitalizationGroup,
  rows: WeeklyIdentityRow[],
): WeeklyIdentityRow[] {
  const byDate = new Map<string, WeeklyIdentityRow[]>();
  for (const row of rows) {
    const literal = validateRow(row);
    if (!group.keys.includes(row.quote_key) || !group.variants.some((variant) =>
      nfcCaseFold(variant) === nfcCaseFold(literal)) ||
      IDENTITY_FIELDS.some((field) => row[field] !== group.cards[0][field]))
      throw new Error("WEEKLY_CAPITALIZATION_IDENTITY_CONFLICT");
    const sameDate = byDate.get(row.observed_on) || [];
    sameDate.push(row);
    byDate.set(row.observed_on, sameDate);
  }

  return [...byDate].sort(([left], [right]) => left.localeCompare(right)).map(([, same]) => {
    const first = same[0];
    if (same.some((row) => row.period_start !== first.period_start ||
        row.details?.period_end !== first.details?.period_end))
      throw new Error("WEEKLY_CAPITALIZATION_PERIOD_CONFLICT");
    if (same.some((row) => row.price !== first.price || row.min_price !== first.min_price ||
        row.max_price !== first.max_price))
      throw new Error("WEEKLY_CAPITALIZATION_PRICE_CONFLICT");
    const primary = same.find((row) => row.quote_key === group.canonicalKey) || first;
    const witnesses = same.map(evidence);
    return {
      ...primary,
      quote_key: group.canonicalKey,
      product_name: group.canonicalName,
      details: {
        ...primary.details,
        original_quote_key: primary.quote_key,
        original_product_name: primary.product_name,
        source_product_literal: sourceProduct(primary),
        capitalization_equivalence_sources: witnesses,
      },
    };
  });
}
