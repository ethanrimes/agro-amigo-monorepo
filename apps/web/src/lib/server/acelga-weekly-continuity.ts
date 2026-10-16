import type { OfficialPrice } from "../official-types";

// Five source-verified literal spellings of one DANE weekly market. Keep this
// finite: other products, daily series and Corabastos quality/ATADO quotes are
// separate publications with different identities.
export const ACELGA_WEEKLY_CANONICAL_KEY =
  "41a589e5022295fd4ed120e045446d49ebeffb79882c6edcc9365d06b63f99f2";
export const ACELGA_WEEKLY_MARKETS: Readonly<Record<string, string>> = {
  "9489a60fd26cc0b726972a558800b3a3f19b9835878d9a9b3875493d4c13da36": "Bogotá, D. C. Corabastos",
  "5fa6938930f5423428f36ef78f2ea03f6a9d7e86b99fa06092d8eb73f128e17e": "Bogotá, D. C., Corabastos",
  [ACELGA_WEEKLY_CANONICAL_KEY]: "Bogotá, D.C., Corabastos",
  "ff7a1ec77432a06d439876b9a16a4eb019209fca7dd49bbf9df922043f1bdc6f": "Bogotá D. C., Corabastos",
  "9d72a8994937aece090517d2e675d058311addbd66d0ba344bf7b4ad7fc17081": "Bogotá, D,C,, Corabastos",
};
export const ACELGA_WEEKLY_KEYS = Object.freeze(Object.keys(ACELGA_WEEKLY_MARKETS));
export const isAcelgaWeeklyKey = (key: string): boolean =>
  Object.prototype.hasOwnProperty.call(ACELGA_WEEKLY_MARKETS, key);
export const isAcelgaWeeklyConflict = (error: unknown): boolean =>
  error instanceof Error &&
  (error.message === "ACELGA_WEEKLY_PRICE_CONFLICT" ||
    error.message === "ACELGA_WEEKLY_IDENTITY_CONFLICT");

function verify(row: OfficialPrice): void {
  const dimensions = row.details?.identity_dimensions;
  if (
    !isAcelgaWeeklyKey(row.quote_key) ||
    row.market !== ACELGA_WEEKLY_MARKETS[row.quote_key] ||
    row.product_id !== "acelga" || row.product_name !== "Acelga" ||
    row.publisher !== "DANE · SIPSA" || row.series !== "dane-weekly" ||
    row.basis !== "Precio mayorista semanal" || row.currency !== "COP" ||
    row.unit !== "kg" || !dimensions || typeof dimensions !== "object" ||
    Array.isArray(dimensions) ||
    Object.keys(dimensions).length !== 1 ||
    (dimensions as Record<string, unknown>).source_product !== "Acelga" ||
    !Number.isFinite(row.price) ||
    (row.min_price !== null && !Number.isFinite(row.min_price)) ||
    (row.max_price !== null && !Number.isFinite(row.max_price))
  ) throw new Error("ACELGA_WEEKLY_IDENTITY_CONFLICT");
}

function provenance(row: OfficialPrice) {
  return {
    quote_key: row.quote_key,
    document_id: row.document_id,
    source_locator: row.source_locator,
    source_page: row.source_page,
    source_url: row.source_url,
    literal_market: row.market,
  };
}

/** One price per date; every original remains intact in the database. */
export function mergeAcelgaWeeklyHistory(rows: OfficialPrice[]): OfficialPrice[] {
  const dates = new Map<string, OfficialPrice[]>();
  for (const row of rows) {
    verify(row);
    const sameDate = dates.get(row.observed_on) || [];
    sameDate.push(row);
    dates.set(row.observed_on, sameDate);
  }
  return [...dates].sort(([a], [b]) => a.localeCompare(b)).map(([, sameDate]) => {
    const [first] = sameDate;
    if (sameDate.some((row) => row.price !== first.price ||
      row.min_price !== first.min_price || row.max_price !== first.max_price ||
      row.currency !== first.currency || row.unit !== first.unit || row.basis !== first.basis))
      throw new Error("ACELGA_WEEKLY_PRICE_CONFLICT");
    // Prefer the exact current market spelling for an overlapping date.
    const primary = sameDate.find((row) => row.quote_key === ACELGA_WEEKLY_CANONICAL_KEY) || sameDate[0];
    return {
      ...primary,
      quote_key: ACELGA_WEEKLY_CANONICAL_KEY,
      market: ACELGA_WEEKLY_MARKETS[ACELGA_WEEKLY_CANONICAL_KEY],
      details: {
        ...primary.details,
        source_market_literal: primary.market,
        original_quote_key: primary.quote_key,
        ...(sameDate.length > 1 ? {
          alternate_originals: sameDate.filter((row) => row !== primary).map(provenance),
        } : {}),
      },
    };
  });
}

export function collapseAcelgaWeeklyCatalog<T extends OfficialPrice & { previous_price: number | null }>(
  cards: T[], history: OfficialPrice[],
): T[] {
  const aliases = cards.filter((card) => isAcelgaWeeklyKey(card.quote_key));
  if (!aliases.length) return cards;
  aliases.forEach(verify);
  const merged = mergeAcelgaWeeklyHistory(history);
  const other = cards.filter((card) => !isAcelgaWeeklyKey(card.quote_key));
  if (!merged.length) return other;
  const latest = merged.at(-1)!;
  return [...other, { ...latest, previous_price: merged.at(-2)?.price ?? null } as T];
}
