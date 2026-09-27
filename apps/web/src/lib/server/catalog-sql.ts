import "server-only";

const today = "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

/** Seek each literal name once, retaining names that occur only in old reports.
 * The date lookup ignores uncurated markets just as CITY_PRICE_QUOTES does.
 */
export const CITY_CATALOG_NAMES_SQL = `WITH RECURSIVE names AS (
  (SELECT product_id,product_name,observed_on,market_name FROM regional_price WHERE observed_on<=${today}
   ORDER BY product_id,product_name,observed_on DESC LIMIT 1)
  UNION ALL
  SELECT n.* FROM names previous CROSS JOIN LATERAL (
    SELECT r.product_id,r.product_name,r.observed_on,r.market_name FROM regional_price r
    WHERE (r.product_id,r.product_name)>(previous.product_id,previous.product_name)
      AND r.observed_on<=${today}
    ORDER BY r.product_id,r.product_name,r.observed_on DESC LIMIT 1
  ) n
) SELECT names.product_id,names.product_name,CASE WHEN names.market_name IN(SELECT name FROM market)
  THEN names.observed_on ELSE (
  SELECT r.observed_on FROM regional_price r
  WHERE r.product_id=names.product_id AND r.product_name=names.product_name
    AND r.observed_on<=${today} AND EXISTS(SELECT 1 FROM market m WHERE m.name=r.market_name)
  ORDER BY r.observed_on DESC LIMIT 1
) END AS latest_date FROM names`;

/** $2 holds candidate products and their latest mapped dates from the name index.
 * Only the winning product date can win the former per-package ranking, so
 * revision and package aggregation happen after that date has been selected.
 */
export const CITY_CATALOG_SQL = `WITH candidates AS MATERIALIZED (
  SELECT product_id,latest_date FROM jsonb_to_recordset($2::jsonb) AS n(product_id text,latest_date date)
), regional_markets AS MATERIALIZED (
  SELECT DISTINCT m.name FROM market m WHERE $1<>'' AND m.region=$1
    AND EXISTS(SELECT 1 FROM regional_price r WHERE r.market_name=m.name AND r.observed_on<=${today})
), dates AS MATERIALIZED (
  SELECT n.product_id,CASE WHEN $1='' THEN n.latest_date ELSE (
    SELECT max(day) FROM (
      SELECT (SELECT r.observed_on FROM regional_price r
        WHERE r.product_id=n.product_id AND r.market_name=m.name AND r.observed_on<=${today}
        ORDER BY r.observed_on DESC LIMIT 1) AS day
      FROM regional_markets m
    ) regional_dates
  ) END AS day FROM candidates n
), quotes AS (
  SELECT DISTINCT ON(r.product_id,m.id,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)))
    r.product_id,m.id AS market_id,r.observed_on,r.min_price,r.max_price,
    upper(left(r.presentation,1)) || lower(substr(r.presentation,2)) AS presentation,
    r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) AS units
  FROM dates n JOIN regional_price r ON r.product_id=n.product_id AND r.observed_on=n.day
  JOIN market m ON m.name=r.market_name JOIN source_document d ON d.id=r.document_id
  WHERE ($1='' OR m.region=$1)
  ORDER BY r.product_id,m.id,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)),r.round DESC,d.retrieved_at DESC,r.source_locator
), grouped AS (
  SELECT product_id,presentation,units,max(observed_on) AS date,
    avg((min_price+max_price)/2) AS price,count(DISTINCT market_id) AS market_count
  FROM quotes GROUP BY product_id,presentation,units
) SELECT DISTINCT ON(p.id) p.*,g.price,NULL::numeric AS previous_price,g.date,g.market_count,
  g.presentation || ' · ' || g.units AS unit,'DANE · informe por ciudad'::text AS source,
  'daily'::text AS period,'city'::text AS series,g.presentation,g.units
FROM grouped g JOIN product p ON p.id=g.product_id
ORDER BY p.id,g.date DESC,g.market_count DESC,g.presentation,g.units`;
