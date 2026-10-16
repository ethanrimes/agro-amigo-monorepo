import { createHash } from "node:crypto";
import type { OfficialPrice } from "../official-types";

// Native Jan 2017 PDF, Feb 2019 PDF/XLS and Oct 2026 PDF agree on the
// facility, variety, unit and statistic. This is a finite identity bridge;
// punctuation changes in other products or markets are not inferred aliases.
export const MINORISTA_WEEKLY_CANONICAL_KEY =
  "0e4aae5e080f2e7265c589a8a2213e7df73e7fbbf1af7d49835b20585a2d520a";
export const MINORISTA_WEEKLY_LEGACY_KEY =
  "f001a4151aff44d99cf4152d060df62e1958acfc360a976c9450f13c2f74eacd";
export const MINORISTA_WEEKLY_MARKETS: Readonly<Record<string, string>> = {
  [MINORISTA_WEEKLY_CANONICAL_KEY]: 'Medellín, Plaza Minorista "José María Villa"',
  [MINORISTA_WEEKLY_LEGACY_KEY]: "Medellín, Plaza Minorista “José María Villa”",
};
export const MINORISTA_WEEKLY_KEYS = Object.freeze(Object.keys(MINORISTA_WEEKLY_MARKETS));
export const isMinoristaWeeklyKey = (key: string): boolean =>
  Object.prototype.hasOwnProperty.call(MINORISTA_WEEKLY_MARKETS, key);
export const isMinoristaWeeklyConflict = (error: unknown): boolean =>
  error instanceof Error && /^(MINORISTA_WEEKLY_IDENTITY|MINORISTA_WEEKLY_PRICE|MINORISTA_WEEKLY_OVERLAP)_CONFLICT$/.test(error.message);

function pythonJson(value: string | Record<string, unknown>): string {
  if (typeof value === "string") return JSON.stringify(value);
  return `{${Object.keys(value).sort().map((key) => `${pythonJson(key)}: ${pythonJson(value[key] as string | Record<string, unknown>)}`).join(", ")}}`;
}

function verify(row: OfficialPrice): void {
  const dims = row.details?.identity_dimensions;
  const identity = { product_id: row.product_id, series: row.series,
    market: row.market, currency: row.currency, unit: row.unit,
    basis: row.basis, dimensions: { source_product: "Limón Tahití" } };
  if (!isMinoristaWeeklyKey(row.quote_key) || row.market !== MINORISTA_WEEKLY_MARKETS[row.quote_key] ||
    row.product_id !== "limon-tahiti" || row.product_name !== "Limón Tahití" ||
    typeof row.category !== "string" || row.category.toLowerCase() !== "frutas frescas" ||
    row.publisher !== "DANE · SIPSA" || row.series !== "dane-weekly" ||
    row.basis !== "Precio mayorista semanal" || row.currency !== "COP" || row.unit !== "kg" ||
    !dims || typeof dims !== "object" || Array.isArray(dims) || Object.keys(dims).length !== 1 ||
    (dims as Record<string, unknown>).source_product !== "Limón Tahití" ||
    createHash("sha256").update(pythonJson(identity), "utf8").digest("hex") !== row.quote_key ||
    !/^\d{4}-\d{2}-\d{2}$/.test(row.observed_on) ||
    !/^[a-f0-9]{64}$/.test(row.document_id) || !row.source_locator ||
    !row.source_url.startsWith("https://www.dane.gov.co/files/") ||
    !Number.isFinite(row.price) || row.price <= 0 ||
    row.min_price === null || !Number.isFinite(row.min_price) ||
    row.max_price === null || !Number.isFinite(row.max_price) ||
    row.min_price <= 0 || row.min_price > row.price || row.price > row.max_price)
    throw new Error("MINORISTA_WEEKLY_IDENTITY_CONFLICT");
}

function original(row: OfficialPrice) {
  return { quote_key: row.quote_key, literal_market: row.market,
    document_id: row.document_id, source_url: row.source_url,
    source_locator: row.source_locator, source_page: row.source_page };
}

/** A failed optional bridge must not hide the other valid bookmarked series.
 * Validate every row of the requested identity independently before retaining
 * its own market, price and provenance. Invalid own rows still fail closed. */
export function standaloneMinoristaWeeklyHistory(rows: OfficialPrice[], id: string): OfficialPrice[] {
  const own = rows.filter((row) => row.quote_key === id);
  own.forEach(verify);
  return own.map((row) => ({ ...row, details: { ...row.details,
    history_continuity_note:
      "Este historial se muestra por separado mientras se verifica una coincidencia entre fuentes." } }));
}

/** Call only on eligible source winners read in a single database snapshot.
 * Fixed anchors establish the alias, rather than restricting new ordinary
 * weekly updates to a past cutoff. Newly discovered cross-key overlaps require
 * independent source review; a conflict affects this bridge alone. */
export function mergeMinoristaWeeklyHistory(rows: OfficialPrice[]): OfficialPrice[] {
  const dates = new Map<string, OfficialPrice[]>();
  for (const row of rows) {
    verify(row);
    const same = dates.get(row.observed_on) || [];
    same.push(row); dates.set(row.observed_on, same);
  }
  return [...dates].sort(([a], [b]) => a.localeCompare(b)).map(([date, same]) => {
    if (same.length > 1 && (date !== "2019-02-15" || same.length !== 2 ||
      new Set(same.map((row) => row.quote_key)).size !== 2))
      throw new Error("MINORISTA_WEEKLY_OVERLAP_CONFLICT");
    const first = same[0];
    if (same.some((row) => row.price !== first.price || row.min_price !== first.min_price ||
      row.max_price !== first.max_price || row.period_start !== first.period_start))
      throw new Error("MINORISTA_WEEKLY_PRICE_CONFLICT");
    const primary = same.find((row) => row.quote_key === MINORISTA_WEEKLY_CANONICAL_KEY) || first;
    return { ...primary, quote_key: MINORISTA_WEEKLY_CANONICAL_KEY,
      market: MINORISTA_WEEKLY_MARKETS[MINORISTA_WEEKLY_CANONICAL_KEY],
      details: { ...primary.details, source_market_literal: primary.market,
        original_quote_key: primary.quote_key,
        ...(same.length > 1 ? { alternate_originals: same.filter((row) => row !== primary).map(original) } : {}) } };
  });
}

type Card = OfficialPrice & { previous_price: number | null };
/** No historical scans for the product catalog; preserve the current card's
 * own previous quote and source. Missing/dirty current metadata cannot supply
 * a current price. The guarded history path resolves the retained originals. */
export function collapseMinoristaWeeklyCatalog(cards: Card[]): Card[] {
  const current = cards.find((row) => row.quote_key === MINORISTA_WEEKLY_CANONICAL_KEY);
  if (!current) return cards;
  cards.filter((row) => isMinoristaWeeklyKey(row.quote_key)).forEach(verify);
  const legacy = cards.find((row) => row.quote_key === MINORISTA_WEEKLY_LEGACY_KEY);
  if (legacy && legacy.observed_on >= current.observed_on)
    throw new Error("MINORISTA_WEEKLY_OVERLAP_CONFLICT");
  return cards.filter((row) => row.quote_key !== MINORISTA_WEEKLY_LEGACY_KEY);
}
