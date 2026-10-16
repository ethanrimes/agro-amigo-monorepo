import { normalizeLabel } from "./label-normalization";
import { fold } from "./planning-math";

export type QuoteMarketChoice = {
  id: string; name: string; literal_name?: string;
  first_report_on?: string | null; last_report_on?: string | null;
};

function reportDate(value?: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  return value.slice(8, 10) + "/" + value.slice(5, 7) + "/" + value.slice(0, 4);
}

/** Source spellings and date coverage distinguish separate historical records.
 * Labels never replace exact market IDs or package selector values. */
export function quoteMarketOptions(markets: QuoteMarketChoice[]) {
  const counts = new Map<string, number>();
  for (const market of markets) {
    const key = fold(market.name);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return markets.map((market) => {
    const first = reportDate(market.first_report_on), last = reportDate(market.last_report_on);
    const details: string[] = [];
    if (first && last) details.push(first === last ? `Informe: ${first}` : `Informes: ${first}–${last}`);
    if ((counts.get(fold(market.name)) || 0) > 1 && market.literal_name)
      details.push(`Nombre en la fuente: ${market.literal_name}`);
    return { id: market.id, label: market.name, ...(details.length ? { detail: details.join(" · ") } : {}) };
  });
}

export function quotePresentationOptions(presentations: string[]) {
  return presentations.map((value) => {
    const label = normalizeLabel(value, "presentation");
    return { id: value, label, ...(label !== value ? { detail: `Texto en la fuente: ${value}` } : {}) };
  });
}
