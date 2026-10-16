import "server-only";
import { database } from "./db";
import { departmentKey, departmentLabel } from "../filter-labels";
import type { OfficialPrice } from "../official-types";

const localMarketSeries = new Set(["dane-daily-query", "dane-weekly", "dane-weekly-pdf", "dane-weekly-xlsx"]);
const localPublishers = new Set(["DANE", "DANE · SIPSA"]);

/** Use exact catalog market geography; never guess a department from city text. */
export async function officialMarketRegions<T extends OfficialPrice>(quotes: T[]): Promise<T[]> {
  const eligible = (quote: T) => localPublishers.has(quote.publisher) && localMarketSeries.has(quote.series);
  const names = [...new Set(quotes.filter(eligible).map((quote) => quote.market))];
  if (!names.length) return quotes;
  const rows = (await database().query<{ name: string; region: string }>(
    "SELECT name,region FROM market WHERE name=ANY($1::text[]) AND region<>''", [names],
  )).rows;
  const regions = new Map<string, Map<string, string>>();
  for (const row of rows) {
    const choices = regions.get(row.name) || new Map<string, string>();
    choices.set(departmentKey(row.region), departmentLabel(row.region));
    regions.set(row.name, choices);
  }
  return quotes.map((quote) => {
    const choices = eligible(quote) ? regions.get(quote.market) : undefined;
    return choices?.size === 1 ? { ...quote, department: [...choices.values()][0] } : quote;
  });
}
