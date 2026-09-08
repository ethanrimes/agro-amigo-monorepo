import "server-only";
import { database, WINDOW } from "./db";
import { CITY_PRICE_QUOTES } from "./price-quotes";
import type {
  Catalog,
  Coffee,
  MarketPrice,
  Point,
  Product,
} from "../market-types";
export async function catalog(region = ""): Promise<Catalog> {
  const db = database();
  const [products, regions, coffeeRows, cityRows] = await Promise.all([
    db.query<Product>(
      `WITH ranked AS (
      SELECT o.*, row_number() OVER w AS rn,
        lead(price) OVER w AS previous_price, lead(observed_on) OVER w AS previous_date
      FROM published_price_observation o JOIN market m ON m.id=o.market_id
      WHERE ${WINDOW} AND o.source_id IN ('dane-sipsa','dane-milk-farm','dane-rice-mill') AND ($1='' OR m.region=$1)
      WINDOW w AS (PARTITION BY o.product_id, o.market_id, o.unit ORDER BY observed_on DESC)
    ), latest AS (
      SELECT *, max(observed_on) OVER (PARTITION BY product_id) AS latest_date FROM ranked WHERE rn=1
    ) SELECT p.*, avg(l.price) AS price,
      CASE WHEN count(l.previous_price) FILTER (WHERE l.previous_date=(date_trunc('month',l.observed_on)-interval '1 day')::date)=count(*)
        THEN avg(l.previous_price) ELSE NULL END AS previous_price,
      max(l.observed_on) AS date, count(*) AS market_count,
      l.unit AS unit, CASE l.source_id WHEN 'dane-milk-farm' THEN 'DANE · leche cruda en finca' WHEN 'dane-rice-mill' THEN 'DANE · molinos · COP/t ÷ 1.000' ELSE 'DANE · SIPSA' END AS source, 'monthly' AS period,
      CASE l.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' ELSE 'monthly' END AS series,
      'Por unidad de medida'::text AS presentation,
      CASE l.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE l.unit END AS units
      FROM product p JOIN latest l ON p.id=l.product_id WHERE l.observed_on=l.latest_date
      GROUP BY p.id,l.unit,l.source_id ORDER BY p.priority, p.name`,
      [region],
    ),
    db.query<{ region: string }>(
      `SELECT region FROM (
        SELECT DISTINCT m.region FROM market m JOIN published_price_observation o ON o.market_id=m.id WHERE o.source_id IN ('dane-sipsa','dane-milk-farm','dane-rice-mill') AND ${WINDOW} AND m.region<>''
        UNION SELECT DISTINCT m.region FROM market m JOIN regional_price r ON r.market_name=m.name WHERE r.observed_on<=CURRENT_DATE AND m.region<>''
      ) regions ORDER BY region`,
    ),
    db.query<Product>(`SELECT 'cafe-pergamino-seco' AS id,'Café pergamino seco' AS name,'Café' AS category,'coffee' AS image_key,
      price,lead(price) OVER(ORDER BY observed_on DESC) AS previous_price,observed_on AS date,16 AS market_count,'125kg' AS unit,'FNC' AS source,'daily' AS period
      FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on DESC LIMIT 1`),
    db.query<Product>(`WITH existing_products AS MATERIALIZED (
      SELECT DISTINCT o.product_id FROM published_price_observation o
      JOIN market existing_market ON existing_market.id=o.market_id
      WHERE o.source_id IN ('dane-sipsa','dane-milk-farm','dane-rice-mill') AND ${WINDOW}
        AND ($1='' OR existing_market.region=$1)
    ), quotes AS (${CITY_PRICE_QUOTES}), choices AS (
      SELECT q.*,max(observed_on) OVER(PARTITION BY product_id,presentation,units) latest
      FROM quotes q WHERE series='city' AND observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AND ($1='' OR region=$1)
      AND q.product_id NOT IN(SELECT product_id FROM existing_products)
    ), grouped AS (
      SELECT product_id,presentation,units,max(observed_on) date,avg(price) price,count(DISTINCT market_id) market_count
      FROM choices WHERE observed_on=latest GROUP BY product_id,presentation,units
    ) SELECT DISTINCT ON(p.id) p.*,g.price,NULL::numeric previous_price,g.date,g.market_count,g.presentation || ' · ' || g.units AS unit,
      'DANE · informe por ciudad'::text source,'daily'::text period,'city'::text series,g.presentation,g.units
      FROM grouped g JOIN product p ON p.id=g.product_id ORDER BY p.id,g.date DESC,g.market_count DESC,g.presentation,g.units`,[region]),
  ]);
  return {
    products: [...coffeeRows.rows, ...products.rows, ...cityRows.rows],
    regions: regions.rows.map((r) => r.region),
    latestDate: [...products.rows,...cityRows.rows].reduce<string | null>(
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
