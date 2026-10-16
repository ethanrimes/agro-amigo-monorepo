import { createHash } from "node:crypto";
import type { OfficialPrice } from "../official-types";

// The retained Nov 2021 XLSX prints "Aguacate Común"; the independently
// checked Jul 2022 PDF prints "Aguacate común" at the same facility, in the
// same weekly COP/kg table. These are the only two source-backed literals.
export const AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY =
  "f22638295418c2adff5055db98cb9231aead214613f06466e17d6c7bd1f1cf17";
export const AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY =
  "d2cd47c7d24f62d9c444252547276897317455211c7568ac404ec623f657b086";
export const AGUACATE_BUCARAMANGA_WEEKLY_LITERALS: Readonly<Record<string, string>> = {
  [AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY]: "Aguacate Común",
  [AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY]: "Aguacate común",
};
export const AGUACATE_BUCARAMANGA_WEEKLY_KEYS = Object.freeze([
  AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY,
  AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY,
]);
export const isAguacateBucaramangaWeeklyKey = (key: string): boolean =>
  Object.prototype.hasOwnProperty.call(AGUACATE_BUCARAMANGA_WEEKLY_LITERALS, key);
export const isAguacateBucaramangaWeeklyConflict = (error: unknown): boolean =>
  error instanceof Error &&
  /^(AGUACATE_BUCARAMANGA_WEEKLY_IDENTITY|AGUACATE_BUCARAMANGA_WEEKLY_OVERLAP)_CONFLICT$/.test(error.message);

function pythonJson(value: string | Record<string, unknown>): string {
  if (typeof value === "string") return JSON.stringify(value);
  return `{${Object.keys(value).sort().map((key) => `${pythonJson(key)}: ${pythonJson(value[key] as string | Record<string, unknown>)}`).join(", ")}}`;
}

function verify(row: OfficialPrice): void {
  const literal = AGUACATE_BUCARAMANGA_WEEKLY_LITERALS[row.quote_key];
  const dimensions = row.details?.identity_dimensions;
  const identity = { product_id: row.product_id, series: row.series,
    market: row.market, currency: row.currency, unit: row.unit,
    basis: row.basis, dimensions: { source_product: literal } };
  if (!literal || row.product_id !== "aguacate-comun" || row.product_name !== literal ||
    row.market !== "Bucaramanga, Centroabastos" || row.publisher !== "DANE · SIPSA" ||
    typeof row.category !== "string" || row.category.toLowerCase() !== "frutas frescas" ||
    row.basis !== "Precio mayorista semanal" || row.currency !== "COP" || row.unit !== "kg" ||
    !dimensions || typeof dimensions !== "object" || Array.isArray(dimensions) ||
    Object.keys(dimensions).length !== 1 ||
    (dimensions as Record<string, unknown>).source_product !== literal ||
    createHash("sha256").update(pythonJson(identity), "utf8").digest("hex") !== row.quote_key ||
    !/^\d{4}-\d{2}-\d{2}$/.test(row.observed_on) ||
    !row.period_start || !/^\d{4}-\d{2}-\d{2}$/.test(row.period_start) ||
    row.period_start > row.observed_on ||
    row.details?.period_type !== "weekly" || row.details?.price_statistic !== "published_mean" ||
    row.details?.period_end !== row.observed_on ||
    !/^[a-f0-9]{64}$/.test(row.document_id) || !row.source_locator ||
    !row.source_url.startsWith("https://www.dane.gov.co/files/") ||
    !Number.isFinite(row.price) || row.price <= 0 ||
    row.min_price === null || !Number.isFinite(row.min_price) || row.min_price <= 0 ||
    row.max_price === null || !Number.isFinite(row.max_price) || row.max_price < row.min_price ||
    row.price < row.min_price || row.price > row.max_price)
    throw new Error("AGUACATE_BUCARAMANGA_WEEKLY_IDENTITY_CONFLICT");
}

function original(row: OfficialPrice) {
  return { quote_key: row.quote_key, literal_product: row.product_name,
    document_id: row.document_id, source_url: row.source_url,
    source_locator: row.source_locator, source_page: row.source_page };
}

/** A failed optional bridge never changes the requested source's own history. */
export function standaloneAguacateBucaramangaWeeklyHistory(rows: OfficialPrice[], id: string): OfficialPrice[] {
  const own = rows.filter((row) => row.quote_key === id);
  own.forEach(verify);
  return own.map((row) => ({ ...row, details: { ...row.details,
    history_continuity_note:
      "Este historial se muestra por separado mientras se verifica una coincidencia entre fuentes." } }));
}

/** Input rows are publication winners from two one-key seeks in one snapshot.
 * A newly overlapping date is accepted only if both full price tuples agree.
 * Both native originals then remain reachable from that date's provenance. */
export function mergeAguacateBucaramangaWeeklyHistory(rows: OfficialPrice[]): OfficialPrice[] {
  const dates = new Map<string, OfficialPrice[]>();
  for (const row of rows) {
    verify(row);
    const same = dates.get(row.observed_on) || [];
    same.push(row); dates.set(row.observed_on, same);
  }
  return [...dates].sort(([a], [b]) => a.localeCompare(b)).map(([, same]) => {
    const first = same[0];
    if (same.length > 2 || (same.length === 2 &&
      new Set(same.map((row) => row.quote_key)).size !== 2) ||
      same.some((row) => row.price !== first.price || row.min_price !== first.min_price ||
        row.max_price !== first.max_price || row.period_start !== first.period_start ||
        row.currency !== first.currency || row.unit !== first.unit || row.basis !== first.basis ||
        row.market !== first.market || row.product_id !== first.product_id))
      throw new Error("AGUACATE_BUCARAMANGA_WEEKLY_OVERLAP_CONFLICT");
    const primary = same.find((row) => row.quote_key === AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY) || first;
    return { ...primary, quote_key: AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY,
      product_name: AGUACATE_BUCARAMANGA_WEEKLY_LITERALS[AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY],
      details: { ...primary.details, source_product_literal: primary.product_name,
        original_quote_key: primary.quote_key,
        ...(same.length > 1 ? { alternate_originals: same.filter((row) => row !== primary).map(original) } : {}) } };
  });
}

type Card = OfficialPrice & { previous_price: number | null };
/** The catalog uses clean current metadata, never a 391-row history scan.
 * A missing/dirty canonical card cannot be replaced with the old 2021 price. */
export function collapseAguacateBucaramangaWeeklyCatalog(cards: Card[]): Card[] {
  const current = cards.find((row) => row.quote_key === AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY);
  const old = cards.find((row) => row.quote_key === AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY);
  if (!old && !current) return cards;
  if (current) verify(current);
  if (old) verify(old);
  if (!current) return cards.filter((row) => row.quote_key !== AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY);
  if (old && old.observed_on >= current.observed_on)
    throw new Error("AGUACATE_BUCARAMANGA_WEEKLY_OVERLAP_CONFLICT");
  return cards.filter((row) => row.quote_key !== AGUACATE_BUCARAMANGA_WEEKLY_OLD_KEY);
}
