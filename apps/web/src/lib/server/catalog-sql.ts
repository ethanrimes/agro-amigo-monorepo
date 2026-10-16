import "server-only";
import { cityFilterUnitsSql, cityDatedIdentityUnitSql } from "./city-package-equivalence";
import { CITY_ALIAS_NAMES_SQL, cityMarketIdSql, cityMarketJoinSql } from "./city-market-alias";
import { verifiedCityCategoryPathSql } from "./category-path-sql";

const today = "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";

/** Seek each literal name once, retaining names that occur only in old reports.
 * The date lookup ignores uncurated markets just as CITY_PRICE_QUOTES does.
 */
export const CITY_CATALOG_NAMES_SQL = `WITH RECURSIVE names AS (
  (SELECT product_id,product_name,observed_on,market_name FROM published_regional_price WHERE observed_on<=${today}
   ORDER BY product_id,product_name,observed_on DESC LIMIT 1)
  UNION ALL
  SELECT n.* FROM names previous CROSS JOIN LATERAL (
    SELECT r.product_id,r.product_name,r.observed_on,r.market_name FROM published_regional_price r
    WHERE (r.product_id,r.product_name)>(previous.product_id,previous.product_name)
      AND r.observed_on<=${today}
    ORDER BY r.product_id,r.product_name,r.observed_on DESC LIMIT 1
  ) n
), identities AS (
  SELECT product_id,product_name FROM names
  UNION
  SELECT corrected_product_id,corrected_product_name
  FROM regional_price_product_correction
)
SELECT i.product_id,i.product_name,dates.latest_date
FROM identities i
CROSS JOIN LATERAL (
  SELECT EXISTS (
    SELECT 1 FROM published_regional_price r WHERE r.product_id=i.product_id
      AND r.product_name=i.product_name AND r.observed_on<=${today}
      AND NOT EXISTS (SELECT 1 FROM regional_price_product_correction c
        WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
  ) OR EXISTS (
    SELECT 1 FROM regional_price_product_correction c
    JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
    WHERE c.corrected_product_id=i.product_id AND c.corrected_product_name=i.product_name
      AND r.observed_on<=${today}
  ) AS present
) valid
CROSS JOIN LATERAL (
  SELECT max(day) AS latest_date FROM (
    (SELECT r.observed_on AS day FROM published_regional_price r
      WHERE r.product_id=i.product_id AND r.product_name=i.product_name
        AND r.observed_on<=${today}
        AND EXISTS(SELECT 1 FROM market m WHERE ${cityMarketJoinSql()})
        AND NOT EXISTS(SELECT 1 FROM regional_price_product_correction c
          WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
      ORDER BY r.observed_on DESC LIMIT 1)
    UNION ALL
    (SELECT r.observed_on AS day FROM regional_price_product_correction c
      JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
      WHERE c.corrected_product_id=i.product_id AND c.corrected_product_name=i.product_name
        AND r.observed_on<=${today}
        AND EXISTS(SELECT 1 FROM market m WHERE ${cityMarketJoinSql()})
      ORDER BY r.observed_on DESC LIMIT 1)
  ) mapped
) dates WHERE valid.present ORDER BY i.product_id,i.product_name`;

/** $2 holds candidate products and their latest mapped dates from the name index.
 * Only the winning product date can win the former per-package ranking, so
 * revision and package aggregation happen after that date has been selected.
 */
export const CITY_CATALOG_SQL = `WITH verified_category AS MATERIALIZED (
  SELECT document_id,source_locator,corrected_category FROM verified_regional_category_overlay
), candidates AS MATERIALIZED (
  SELECT product_id,latest_date FROM jsonb_to_recordset($2::jsonb) AS n(product_id text,latest_date date)
), regional_markets AS MATERIALIZED (
  SELECT DISTINCT source_name.market_name AS name FROM market m
    CROSS JOIN LATERAL (SELECT m.name AS market_name UNION ALL
      SELECT 'Bogotà, Corabastos' WHERE m.id='sipsa-bogota-d-c-corabastos' AND m.municipality_id='11001') source_name
    WHERE $1<>'' AND
    translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($1)),'ÁÉÍÓÚÜÑ','áéíóúüñ')
), regional_dates AS MATERIALIZED (
  SELECT product_id,max(observed_on) AS day FROM (
    SELECT n.product_id,latest.observed_on
    FROM candidates n CROSS JOIN regional_markets m
    CROSS JOIN LATERAL (
      SELECT r.observed_on FROM published_regional_price r
      WHERE r.product_id=n.product_id AND r.market_name=m.name
        AND r.observed_on<=${today}
        AND NOT EXISTS(SELECT 1 FROM regional_price_product_correction c
          WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
      ORDER BY r.observed_on DESC LIMIT 1
    ) latest
    UNION ALL
    SELECT c.corrected_product_id,r.observed_on
    FROM candidates n JOIN regional_price_product_correction c ON c.corrected_product_id=n.product_id
    JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
    JOIN regional_markets m ON m.name=r.market_name
    WHERE $1<>'' AND r.observed_on<=${today}
  ) regional_rows GROUP BY product_id
), dates AS MATERIALIZED (
  SELECT n.product_id,CASE WHEN $1='' THEN n.latest_date ELSE r.day END AS day
  FROM candidates n LEFT JOIN regional_dates r ON r.product_id=n.product_id
), quote_rows AS MATERIALIZED (
  SELECT r.* FROM dates n JOIN published_regional_price r
    ON r.product_id=n.product_id AND r.observed_on=n.day
  WHERE NOT EXISTS(SELECT 1 FROM regional_price_product_correction c
    WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
  UNION ALL
  SELECT r.document_id,r.source_locator,r.observed_on,
    c.corrected_product_id,c.corrected_product_name,r.market_name,r.category,
    r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
    r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
  FROM dates n JOIN regional_price_product_correction c ON c.corrected_product_id=n.product_id
  JOIN published_regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
    AND r.observed_on=n.day
), alias_keys AS MATERIALIZED (
  SELECT DISTINCT r.product_id,r.observed_on,lower(btrim(r.presentation)) AS presentation_key,
    r.quantity,lower(btrim(r.source_unit)) AS source_unit_key,r.unit,r.round
  FROM quote_rows r WHERE r.market_name IN ${CITY_ALIAS_NAMES_SQL}
), alias_latest AS MATERIALIZED (
  SELECT DISTINCT ON (k.product_id,k.observed_on,k.presentation_key,k.quantity,
      k.source_unit_key,k.unit,k.round,rival.market_name)
    k.product_id,k.observed_on,k.presentation_key,k.quantity,k.source_unit_key,k.unit,k.round,
    rival.market_name,rival.min_price,rival.max_price,
    (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
    (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
    ${verifiedCityCategoryPathSql('rival_overlay','rival_class.category_path','rival')} AS category_path
  FROM alias_keys k JOIN published_regional_price rival
    ON rival.observed_on=k.observed_on
    AND lower(btrim(rival.presentation))=k.presentation_key
    AND rival.quantity=k.quantity AND lower(btrim(rival.source_unit))=k.source_unit_key
    AND rival.unit=k.unit AND rival.round=k.round
  JOIN source_document rival_d ON rival_d.id=rival.document_id
  LEFT JOIN regional_price_product_correction rival_c
    ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
  LEFT JOIN regional_classification rival_class
    ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
  LEFT JOIN verified_category rival_overlay
    ON rival_overlay.document_id=rival.document_id AND rival_overlay.source_locator=rival.source_locator
  WHERE rival.market_name IN ${CITY_ALIAS_NAMES_SQL}
    AND coalesce(rival_c.corrected_product_id,rival.product_id)=k.product_id
  ORDER BY k.product_id,k.observed_on,k.presentation_key,k.quantity,k.source_unit_key,
    k.unit,k.round,rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
), alias_conflicts AS (
  SELECT product_id,observed_on,presentation_key,quantity,source_unit_key,unit,round
  FROM alias_latest
  GROUP BY product_id,observed_on,presentation_key,quantity,source_unit_key,unit,round
  HAVING count(DISTINCT market_name)>1
    AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
), quotes AS (
  SELECT DISTINCT ON(r.product_id,${cityMarketIdSql()},lower(btrim(r.presentation)),r.quantity,${cityDatedIdentityUnitSql()})
    r.product_id,${cityMarketIdSql()} AS market_id,r.observed_on,r.min_price,r.max_price,
    r.document_id,r.source_locator,r.category,
    upper(left(r.presentation,1)) || lower(substr(r.presentation,2)) AS presentation,
    ${cityFilterUnitsSql()} AS units
  FROM quote_rows r
  JOIN market m ON ${cityMarketJoinSql()} JOIN source_document d ON d.id=r.document_id
  WHERE ($1='' OR translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($1)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
    AND NOT CASE WHEN (m.municipality_id='11001' AND m.name IN ${CITY_ALIAS_NAMES_SQL}) THEN EXISTS (
      SELECT 1 FROM alias_conflicts conflict
      WHERE conflict.product_id=r.product_id AND conflict.observed_on=r.observed_on
        AND conflict.presentation_key=lower(btrim(r.presentation))
        AND conflict.quantity=r.quantity AND conflict.source_unit_key=lower(btrim(r.source_unit))
        AND conflict.unit=r.unit AND conflict.round=r.round
    ) ELSE false END
  ORDER BY r.product_id,${cityMarketIdSql()},lower(btrim(r.presentation)),r.quantity,${cityDatedIdentityUnitSql()},r.round DESC,d.retrieved_at DESC,r.source_locator
), classified_quotes AS (
  SELECT q.*,${verifiedCityCategoryPathSql('category_overlay','c.category_path','q')} AS category_path
  FROM quotes q LEFT JOIN verified_category category_overlay
    ON category_overlay.document_id=q.document_id AND category_overlay.source_locator=q.source_locator
  LEFT JOIN regional_classification c
    ON c.document_id=q.document_id AND c.source_locator=q.source_locator
), grouped AS (
  SELECT product_id,presentation,units,max(observed_on) AS date,
    avg((min_price+max_price)/2) AS price,count(DISTINCT market_id) AS market_count
  FROM classified_quotes GROUP BY product_id,presentation,units
), paths AS (
  SELECT product_id,
    jsonb_agg(DISTINCT to_jsonb(category_path) ORDER BY to_jsonb(category_path)) AS category_paths
  FROM classified_quotes GROUP BY product_id
) SELECT DISTINCT ON(p.id) p.*,g.price,NULL::numeric AS previous_price,g.date,g.market_count,
  g.presentation || ' · ' || g.units AS unit,'DANE · informe por ciudad'::text AS source,
  'daily'::text AS period,'city'::text AS series,g.presentation,g.units,paths.category_paths
FROM grouped g JOIN product p ON p.id=g.product_id JOIN paths ON paths.product_id=g.product_id
ORDER BY p.id,g.date DESC,g.market_count DESC,g.presentation,g.units`;
