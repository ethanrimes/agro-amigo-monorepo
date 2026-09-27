import "server-only";
import { database, WINDOW } from "./db";
import { CITY_CATALOG_SQL } from "./catalog-sql";
import { cityCatalogNames } from "./city-catalog-names";
import { monthlyCatalogSnapshot } from "./monthly-catalog";
import type {
  Catalog,
  Coffee,
  MarketPrice,
  Point,
  Product,
} from "../market-types";
export async function catalog(region = ""): Promise<Catalog & { cacheExpiresAt: number }> {
  const db = database();
  const [monthly, coffeeRows, names] = await Promise.all([
    monthlyCatalogSnapshot(),
    db.query<Product>(`SELECT 'cafe-pergamino-seco' AS id,'Café pergamino seco' AS name,'Café' AS category,'coffee' AS image_key,
      price,lead(price) OVER(ORDER BY observed_on DESC) AS previous_price,observed_on AS date,16 AS market_count,'125kg' AS unit,'FNC' AS source,'daily' AS period
      FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on DESC LIMIT 1`),
    cityCatalogNames(),
  ]);
  const products = monthly.products.get(region) || [];
  const existing = new Set(products.map((row) => row.id));
  const dates = new Map<string, string>();
  for (const row of names) {
    if (!existing.has(row.product_id) && row.latest_date && row.latest_date > (dates.get(row.product_id) || "")) {
      dates.set(row.product_id, row.latest_date);
    }
  }
  const candidates = [...dates].map(([product_id, latest_date]) => ({ product_id, latest_date }));
  const cityRows = candidates.length
    ? await db.query<Product>(CITY_CATALOG_SQL, [region, JSON.stringify(candidates)])
    : { rows: [] as Product[] };
  return {
    cacheExpiresAt: monthly.expiresAt,
    products: [...coffeeRows.rows, ...products, ...cityRows.rows],
    regions: monthly.regions,
    latestDate: [...products,...cityRows.rows].reduce<string | null>(
      (d, p) => (!d || p.date > d ? p.date : d),
      null,
    ),
  };
}
export async function coffee(): Promise<Coffee | null> {
  const db = database();
  const [reference, markets, factors, exchange] = await Promise.all([
    db.query<Point & { source_url: string }>(
      `SELECT observed_on AS date, price, source_url, document_id FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on`,
    ),
    db.query<MarketPrice>(
      `SELECT DISTINCT ON (m.id) m.*, o.product_id, o.price, o.min_price, o.max_price, o.observed_on AS date, o.source_url, o.document_id, o.source_locator, o.period, o.unit FROM published_price_observation o JOIN market m ON m.id=o.market_id WHERE source_id='fnc' AND ${WINDOW} ORDER BY m.id, o.observed_on DESC`,
    ),
    db.query<{ factor: number; price: number; date: string }>(
      `SELECT factor, price, observed_on AS date FROM coffee_factor WHERE observed_on=(SELECT max(observed_on) FROM coffee_factor WHERE ${WINDOW}) ORDER BY factor`,
    ),
    db.query<{ price: number; date: string; source_url: string }>(
      `SELECT price, observed_on AS date, source_url FROM exchange_rate WHERE ${WINDOW} ORDER BY observed_on DESC LIMIT 1`,
    ),
  ]);
  const latest = reference.rows.at(-1);
  if (!latest) return null;
  return {
    ...latest,
    previous_price: reference.rows.at(-2)?.price ?? null,
    history: reference.rows,
    markets: markets.rows,
    factors: factors.rows,
    exchange: exchange.rows[0] ?? null,
  };
}
