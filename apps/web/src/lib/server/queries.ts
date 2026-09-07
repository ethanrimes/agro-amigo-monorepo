import "server-only";
import { database, WINDOW } from "./db";
import type {
  Catalog,
  Coffee,
  MarketPrice,
  Point,
  Product,
} from "../market-types";
export async function catalog(region = ""): Promise<Catalog> {
  const db = database();
  const [products, regions, coffeeRows] = await Promise.all([
    db.query<Product>(
      `WITH ranked AS (
      SELECT o.*, row_number() OVER w AS rn,
        lead(price) OVER w AS previous_price, lead(observed_on) OVER w AS previous_date
      FROM price_observation o JOIN market m ON m.id=o.market_id
      WHERE ${WINDOW} AND o.source_id='dane-sipsa' AND ($1='' OR m.region=$1)
      WINDOW w AS (PARTITION BY o.product_id, o.market_id ORDER BY observed_on DESC)
    ), latest AS (
      SELECT *, max(observed_on) OVER (PARTITION BY product_id) AS latest_date FROM ranked WHERE rn=1
    ) SELECT p.*, avg(l.price) AS price,
      CASE WHEN count(l.previous_price) FILTER (WHERE l.previous_date=(date_trunc('month',l.observed_on)-interval '1 day')::date)=count(*)
        THEN avg(l.previous_price) ELSE NULL END AS previous_price,
      max(l.observed_on) AS date, count(*) AS market_count,
      'kg' AS unit, 'DANE · SIPSA' AS source, 'monthly' AS period
      FROM product p JOIN latest l ON p.id=l.product_id WHERE l.observed_on=l.latest_date
      GROUP BY p.id ORDER BY p.priority, p.name`,
      [region],
    ),
    db.query<{ region: string }>(
      `SELECT DISTINCT m.region FROM market m JOIN price_observation o ON o.market_id=m.id WHERE o.source_id='dane-sipsa' AND ${WINDOW} AND m.region<>'' ORDER BY m.region`,
    ),
    db.query<Product>(`SELECT 'cafe-pergamino-seco' AS id,'Café pergamino seco' AS name,'Café' AS category,'coffee' AS image_key,
      price,lead(price) OVER(ORDER BY observed_on DESC) AS previous_price,observed_on AS date,16 AS market_count,'125kg' AS unit,'FNC' AS source,'daily' AS period
      FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on DESC LIMIT 1`),
  ]);
  return {
    products: [...coffeeRows.rows, ...products.rows],
    regions: regions.rows.map((r) => r.region),
    latestDate: products.rows.reduce<string | null>(
      (d, p) => (!d || p.date > d ? p.date : d),
      null,
    ),
  };
}
export async function productDetail(id: string, region = "") {
  const db = database();
  const product = await db.query("SELECT * FROM product WHERE id=$1", [id]);
  if (!product.rows[0]) return null;
  const [markets, history] = await Promise.all([
    db.query<MarketPrice>(
      `SELECT DISTINCT ON (m.id) m.*, o.product_id, o.price, o.min_price, o.max_price, o.observed_on AS date, o.source_url, o.document_id, o.source_locator, o.period, o.unit FROM price_observation o JOIN market m ON m.id=o.market_id WHERE product_id=$1 AND ${WINDOW} AND ($2='' OR m.region=$2) ORDER BY m.id, o.observed_on DESC`,
      [id, region],
    ),
    db.query<Point>(
      `SELECT observed_on AS date, avg(price) AS price FROM price_observation o JOIN market m ON m.id=o.market_id WHERE product_id=$1 AND ${WINDOW} AND ($2='' OR m.region=$2) GROUP BY observed_on ORDER BY observed_on`,
      [id, region],
    ),
  ]);
  return {
    product: product.rows[0],
    markets: markets.rows,
    history: history.rows,
  };
}
export async function coffee(): Promise<Coffee | null> {
  const db = database();
  const [reference, markets, factors, exchange] = await Promise.all([
    db.query<Point & { source_url: string }>(
      `SELECT observed_on AS date, price, source_url, document_id FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on`,
    ),
    db.query<MarketPrice>(
      `SELECT DISTINCT ON (m.id) m.*, o.product_id, o.price, o.min_price, o.max_price, o.observed_on AS date, o.source_url, o.document_id, o.source_locator, o.period, o.unit FROM price_observation o JOIN market m ON m.id=o.market_id WHERE source_id='fnc' AND ${WINDOW} ORDER BY m.id, o.observed_on DESC`,
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
