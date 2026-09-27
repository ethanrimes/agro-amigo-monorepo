import "server-only";
import { database, WINDOW } from "./db";
import type { Product } from "../market-types";

export const RECENT_MONTHLY_QUOTES_SQL = `SELECT o.product_id,o.market_id,o.source_id,
  o.unit,o.price::text AS price,o.observed_on::text AS observed_on,m.region
  FROM published_price_observation o JOIN market m ON m.id=o.market_id
  WHERE ${WINDOW} AND o.source_id IN ('dane-sipsa','dane-milk-farm','dane-rice-mill')`;
export const CATALOG_MARKETS_SQL = `SELECT m.region,EXISTS(
  SELECT 1 FROM regional_price r WHERE r.market_name=m.name
    AND r.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  ) AS has_city FROM market m WHERE m.region<>'' ORDER BY m.region`;
export const CATALOG_PRODUCTS_SQL = "SELECT * FROM product ORDER BY priority,name";

export type MonthlyQuote = {
  product_id: string; market_id: string; source_id: string; unit: string;
  price: string; observed_on: string; region: string;
};
export type CatalogProductMetadata = Pick<Product, "id" | "name" | "category" | "image_key"> & { priority: number };
export type CatalogMarket = { region: string; has_city: boolean };
export type MonthlyCatalogValues = { products: Map<string, Product[]>; regions: string[] };
export type MonthlyCatalogSnapshot = MonthlyCatalogValues & { expiresAt: number };
type LatestPair = { current: MonthlyQuote; previous?: MonthlyQuote };

function cents(value: string): bigint {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) throw new Error("INVALID_CATALOG_PRICE");
  return BigInt(match[1]) * BigInt(100) + BigInt((match[2] || "").padEnd(2, "0"));
}
const power10 = (n: number) => BigInt(10) ** BigInt(n);

/** Match PostgreSQL numeric AVG's division scale and rounding, then convert the
 * final decimal once, as the pg numeric-to-Number type parser does. All sums are
 * integer cents, including totals larger than JavaScript's safe integer range.
 */
export function averageCents(total: bigint, count: number): number {
  if (!count) throw new Error("EMPTY_CATALOG_AVERAGE");
  if (total === BigInt(0)) return 0;
  const weight1 = Math.floor((total.toString().length - 3) / 4);
  const exponent1 = 2 + 4 * weight1;
  const first1 = exponent1 < 0 ? total * power10(-exponent1) : total / power10(exponent1);
  const divisor = BigInt(count);
  const weight2 = Math.floor((divisor.toString().length - 1) / 4);
  const first2 = divisor / power10(4 * weight2);
  const quotientWeight = weight1 - weight2 - (first1 <= first2 ? 1 : 0);
  const scale = Math.max(2, 16 - 4 * quotientWeight);
  const denominator = divisor * BigInt(100);
  const numerator = total * power10(scale);
  let rounded = numerator / denominator;
  if ((numerator % denominator) * BigInt(2) >= denominator) rounded += BigInt(1);
  const digits = rounded.toString().padStart(scale + 1, "0");
  return Number(digits.slice(0, -scale) + "." + digits.slice(-scale));
}

function previousMonthEnd(day: string): string {
  const date = new Date(day.slice(0, 7) + "-01T00:00:00Z");
  date.setUTCDate(0);
  return date.toISOString().slice(0, 10);
}

/** Same identities as the SQL oracle: latest row per product/market/unit,
 * then only markets reporting that product's latest date in the chosen region.
 * Equal-date rows count as the preceding row, so they cannot imply a valid
 * previous-month comparison. Sources and units remain separate in aggregates.
 */
export function aggregateMonthlyCatalog(
  quotes: MonthlyQuote[], metadata: CatalogProductMetadata[], markets: CatalogMarket[],
): MonthlyCatalogValues {
  const latest = new Map<string, LatestPair>();
  const reportedRegions = new Set<string>();
  for (const quote of quotes) {
    reportedRegions.add(quote.region);
    const key = JSON.stringify([quote.product_id, quote.market_id, quote.unit]);
    const pair = latest.get(key);
    if (!pair) latest.set(key, { current: quote });
    else if (quote.observed_on > pair.current.observed_on) {
      pair.previous = pair.current;
      pair.current = quote;
    } else if (!pair.previous || quote.observed_on > pair.previous.observed_on) pair.previous = quote;
  }
  const productDays = new Map<string, Map<string, string>>();
  for (const { current } of latest.values()) {
    for (const region of current.region ? ["", current.region] : [""]) {
      let days = productDays.get(region);
      if (!days) productDays.set(region, days = new Map());
      if (current.observed_on > (days.get(current.product_id) || "")) days.set(current.product_id, current.observed_on);
    }
  }
  type Aggregate = { quote: MonthlyQuote; total: bigint; previous: bigint; previousCount: number; count: number };
  const grouped = new Map<string, Map<string, Aggregate>>();
  for (const { current, previous } of latest.values()) {
    const price = cents(current.price);
    const previousPrice = previous?.observed_on === previousMonthEnd(current.observed_on) ? cents(previous.price) : null;
    for (const region of current.region ? ["", current.region] : [""]) {
      if (current.observed_on !== productDays.get(region)?.get(current.product_id)) continue;
      let groups = grouped.get(region);
      if (!groups) grouped.set(region, groups = new Map());
      const key = JSON.stringify([current.product_id, current.unit, current.source_id]);
      let group = groups.get(key);
      if (!group) groups.set(key, group = { quote: current, total: BigInt(0), previous: BigInt(0), previousCount: 0, count: 0 });
      group.total += price;
      group.count++;
      if (previousPrice !== null) { group.previous += previousPrice; group.previousCount++; }
    }
  }
  const products = new Map<string, Product[]>();
  const metadataById = new Map(metadata.map((p) => [p.id, p]));
  const ordering = new Map(metadata.map((p, index) => [p.id, index]));
  for (const [region, groups] of grouped) {
    const rows: Product[] = [];
    for (const group of groups.values()) {
      const quote = group.quote, product = metadataById.get(quote.product_id);
      if (!product) continue;
      const milk = quote.source_id === "dane-milk-farm", rice = quote.source_id === "dane-rice-mill";
      rows.push({ ...product, price: averageCents(group.total, group.count),
        previous_price: group.previousCount === group.count ? averageCents(group.previous, group.count) : null,
        date: quote.observed_on, market_count: group.count, unit: quote.unit,
        source: milk ? "DANE · leche cruda en finca" : rice ? "DANE · molinos · COP/t ÷ 1.000" : "DANE · SIPSA",
        period: "monthly", series: milk ? "farmgate" : rice ? "mill" : "monthly",
        presentation: "Por unidad de medida",
        units: ({ kg: "1 kg", litre: "1 litro", unit: "1 unidad", "125kg": "Carga de 125 kg" } as Record<string, string>)[quote.unit] || quote.unit,
      });
    }
    rows.sort((a, b) => ordering.get(a.id)! - ordering.get(b.id)!);
    products.set(region, rows);
  }
  // Market metadata is ordered by the database's collation, just like the SQL
  // UNION used previously; all historical city departments remain available.
  const regions = [...new Set(markets.filter((m) => m.has_city || reportedRegions.has(m.region)).map((m) => m.region))];
  return { products, regions };
}

let snapshot: MonthlyCatalogSnapshot | undefined;
let pending: Promise<MonthlyCatalogSnapshot> | undefined;
/** One bounded recent-row read shared by every department and concurrent caller.
 * All reads share a repeatable read transaction, including product metadata.
 * Publish the snapshot only after every read and the complete aggregation pass.
 * Failed/expired refreshes reject; no partial or silently stale fallback is used.
 */
export async function monthlyCatalogSnapshot(): Promise<MonthlyCatalogSnapshot> {
  if (snapshot && snapshot.expiresAt > Date.now()) return snapshot;
  if (pending) return pending;
  pending = (async () => {
    const client = await database().connect();
    try {
      await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
      const quotes = await client.query<MonthlyQuote>(RECENT_MONTHLY_QUOTES_SQL);
      const products = await client.query<CatalogProductMetadata>(CATALOG_PRODUCTS_SQL);
      const markets = await client.query<CatalogMarket>(CATALOG_MARKETS_SQL);
      const value = aggregateMonthlyCatalog(quotes.rows, products.rows, markets.rows);
      await client.query("COMMIT");
      snapshot = { ...value, expiresAt: Date.now() + 300_000 };
      return snapshot;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  })().finally(() => { pending = undefined; });
  return pending;
}
