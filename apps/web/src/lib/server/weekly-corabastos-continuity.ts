import { createHash } from "node:crypto";
import type { OfficialPrice } from "../official-types";

// These five spellings are independently visible in retained DANE weekly
// originals. The four red-egg grades have an explicit $/unidad footnote in
// both verified annexes; other non-kg products remain outside this bridge.
export const WEEKLY_CORABASTOS_CANONICAL_MARKET = "Bogotá, D.C., Corabastos";
export const WEEKLY_CORABASTOS_MARKETS = new Set([
  "Bogotá, D. C. Corabastos",
  "Bogotá, D. C., Corabastos",
  WEEKLY_CORABASTOS_CANONICAL_MARKET,
  "Bogotá D. C., Corabastos",
  "Bogotá, D,C,, Corabastos",
]);
export const WEEKLY_CORABASTOS_UNIT_EGGS: Readonly<Record<string, string>> = {
  "huevo-rojo-a": "Huevo rojo A",
  "huevo-rojo-aa": "Huevo rojo AA",
  "huevo-rojo-b": "Huevo rojo B",
  "huevo-rojo-extra": "Huevo rojo extra",
};

type Card = OfficialPrice & { previous_price: number | null };
export type WeeklyCorabastosGroup = { canonicalKey: string; cards: Card[]; keys: string[] };

// Match official_sources.py's sorted-key, non-ASCII-escaped Python json.dumps
// for the supported source_product-only identity object.
function pythonJson(value: string | Record<string, unknown>): string {
  if (typeof value === "string") return JSON.stringify(value);
  return `{${Object.keys(value).sort().map((key) => `${pythonJson(key)}: ${pythonJson(value[key] as string | Record<string, unknown>)}`).join(", ")}}`;
}

function sourceProduct(row: OfficialPrice): string | null {
  const dimensions = row.details?.identity_dimensions;
  if (!dimensions || typeof dimensions !== "object" || Array.isArray(dimensions) ||
      Object.keys(dimensions).length !== 1) return null;
  const value = (dimensions as Record<string, unknown>).source_product;
  return typeof value === "string" && value === row.product_name ? value : null;
}

export function expectedWeeklyCorabastosKey(row: OfficialPrice): string | null {
  const name = sourceProduct(row);
  const auditedEgg = Object.prototype.hasOwnProperty.call(WEEKLY_CORABASTOS_UNIT_EGGS, row.product_id);
  const unitVerified = (row.unit === "kg" && !auditedEgg) ||
    (row.unit === "unit" && WEEKLY_CORABASTOS_UNIT_EGGS[row.product_id] === row.product_name);
  if (!name || !WEEKLY_CORABASTOS_MARKETS.has(row.market) ||
      row.publisher !== "DANE · SIPSA" || row.series !== "dane-weekly" ||
      row.basis !== "Precio mayorista semanal" || row.currency !== "COP" ||
      !unitVerified || !row.product_id) return null;
  const identity = { product_id: row.product_id, series: row.series,
    market: row.market, currency: row.currency, unit: row.unit,
    basis: row.basis, dimensions: { source_product: name } };
  return createHash("sha256").update(pythonJson(identity), "utf8").digest("hex");
}

function fingerprint(row: OfficialPrice): string {
  return pythonJson({ product_id: row.product_id, product_name: row.product_name,
    publisher: row.publisher, series: row.series, basis: row.basis,
    currency: row.currency, unit: row.unit,
    dimensions: { source_product: sourceProduct(row) } });
}

export function weeklyCorabastosGroups(cards: Card[]): {
  groups: WeeklyCorabastosGroup[]; byKey: Map<string, WeeklyCorabastosGroup>;
} {
  const candidates = new Map<string, Card[]>();
  const tainted = new Set<string>();
  for (const card of cards) {
    const expected = expectedWeeklyCorabastosKey(card);
    if (!expected) continue;
    const identity = fingerprint(card);
    if (expected !== card.quote_key) { tainted.add(identity); continue; }
    const group = candidates.get(identity) || [];
    group.push(card);
    candidates.set(identity, group);
  }
  const groups: WeeklyCorabastosGroup[] = [], byKey = new Map<string, WeeklyCorabastosGroup>();
  for (const [identity, groupCards] of candidates) {
    if (tainted.has(identity)) continue;
    if (groupCards.length < 2 || new Set(groupCards.map((card) => card.market)).size < 2) continue;
    const canonical = groupCards.find((card) => card.market === WEEKLY_CORABASTOS_CANONICAL_MARKET);
    if (!canonical || new Set(groupCards.map((card) => card.market)).size !== groupCards.length) continue;
    const group = { canonicalKey: canonical.quote_key, cards: groupCards,
      keys: groupCards.map((card) => card.quote_key) };
    groups.push(group);
    for (const key of group.keys) byKey.set(key, group);
  }
  return { groups, byKey };
}

export function isWeeklyCorabastosConflict(error: unknown): boolean {
  return error instanceof Error && (
    error.message === "WEEKLY_CORABASTOS_IDENTITY_CONFLICT" ||
    error.message === "WEEKLY_CORABASTOS_PRICE_CONFLICT");
}

function checkRow(row: OfficialPrice, group: WeeklyCorabastosGroup): void {
  if (!group.keys.includes(row.quote_key) ||
      expectedWeeklyCorabastosKey(row) !== row.quote_key ||
      fingerprint(row) !== fingerprint(group.cards[0]) ||
      !Number.isFinite(row.price) ||
      (row.min_price !== null && !Number.isFinite(row.min_price)) ||
      (row.max_price !== null && !Number.isFinite(row.max_price)))
    throw new Error("WEEKLY_CORABASTOS_IDENTITY_CONFLICT");
}

function origin(row: OfficialPrice) {
  return { quote_key: row.quote_key, document_id: row.document_id,
    source_locator: row.source_locator, source_page: row.source_page,
    source_url: row.source_url, literal_market: row.market };
}

export function mergeWeeklyCorabastosHistory(group: WeeklyCorabastosGroup, rows: OfficialPrice[]): OfficialPrice[] {
  const dates = new Map<string, OfficialPrice[]>();
  for (const row of rows) {
    checkRow(row, group);
    const same = dates.get(row.observed_on) || [];
    same.push(row); dates.set(row.observed_on, same);
  }
  return [...dates].sort(([a], [b]) => a.localeCompare(b)).map(([, same]) => {
    const first = same[0];
    if (same.some((row) => row.price !== first.price || row.min_price !== first.min_price ||
      row.max_price !== first.max_price || row.currency !== first.currency ||
      row.unit !== first.unit || row.basis !== first.basis))
      throw new Error("WEEKLY_CORABASTOS_PRICE_CONFLICT");
    const primary = same.find((row) => row.quote_key === group.canonicalKey) || first;
    return { ...primary, quote_key: group.canonicalKey,
      market: WEEKLY_CORABASTOS_CANONICAL_MARKET,
      details: { ...primary.details, source_market_literal: primary.market,
        original_quote_key: primary.quote_key,
        ...(same.length > 1 ? { alternate_originals: same.filter((row) => row !== primary).map(origin) } : {}) } };
  });
}

/** Catalog only uses current payload metadata; no per-group history scans. */
export function collapseWeeklyCorabastosCatalog(cards: Card[], groups: WeeklyCorabastosGroup[]): Card[] {
  const grouped = new Set(groups.flatMap((group) => group.keys));
  const output = cards.filter((card) => !grouped.has(card.quote_key));
  for (const group of groups) {
    const latestDay = group.cards.reduce((date, card) => card.observed_on > date ? card.observed_on : date, "");
    const latest = group.cards.filter((card) => card.observed_on === latestDay);
    const first = latest[0];
    if (latest.some((card) => card.price !== first.price || card.min_price !== first.min_price ||
      card.max_price !== first.max_price || card.currency !== first.currency ||
      card.unit !== first.unit || card.basis !== first.basis)) continue;
    const primary = latest.find((card) => card.quote_key === group.canonicalKey) || first;
    output.push({ ...primary, quote_key: group.canonicalKey,
      market: WEEKLY_CORABASTOS_CANONICAL_MARKET, previous_price: null,
      details: { ...primary.details, source_market_literal: primary.market,
        original_quote_key: primary.quote_key,
        ...(latest.length > 1 ? { alternate_originals: latest.filter((card) => card !== primary).map(origin) } : {}) } });
  }
  return output;
}
