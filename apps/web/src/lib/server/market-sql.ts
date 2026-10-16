/** Count identities before loading any quote payload, package or classification. */
import { CITY_ALIAS_NAMES_SQL, cityMarketIdSql, cityMarketJoinSql, cityMarketNamesForIdSql } from "./city-market-alias";
import { verifiedCityCategoryPathSql } from "./category-path-sql";

/** Compare the latest literal witnesses once per typed key. A correlated rival
 * seek for every quote repeats the same work across all dates in the directory.
 * Keep the publication view, corrected identities, package dimensions, source
 * ranking and classification witnesses identical to the quote conflict rule.
 */
export function cityAliasConflicts(dateWindow: string) {
  return `city_alias_witnesses AS MATERIALIZED (
      SELECT rival.document_id,rival.source_locator,rival_d.retrieved_at,
        coalesce(rival_c.corrected_product_id,rival.product_id) AS product_id,
        rival.observed_on,lower(btrim(rival.presentation)) AS presentation_key,
        rival.quantity,lower(btrim(rival.source_unit)) AS source_unit_key,
        rival.unit,rival.round,rival.market_name,rival.min_price,rival.max_price,
        (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
        (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
        ${verifiedCityCategoryPathSql('rival_overlay','rival_class.category_path','rival')} AS category_path
      FROM published_regional_price rival
      JOIN source_document rival_d ON rival_d.id=rival.document_id
      LEFT JOIN regional_classification rival_class
        ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
      LEFT JOIN verified_regional_category_overlay rival_overlay
        ON rival_overlay.document_id=rival.document_id AND rival_overlay.source_locator=rival.source_locator
      LEFT JOIN regional_price_product_correction rival_c
        ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
      WHERE rival.market_name IN ${CITY_ALIAS_NAMES_SQL} AND ${dateWindow}
  ), city_alias_conflicts AS MATERIALIZED (
    SELECT product_id,observed_on,presentation_key,quantity,source_unit_key,unit,round
    FROM (
      SELECT DISTINCT ON (product_id,observed_on,presentation_key,quantity,
        source_unit_key,unit,round,market_name) *
      FROM city_alias_witnesses
      ORDER BY product_id,observed_on,presentation_key,quantity,source_unit_key,
        unit,round,market_name,retrieved_at DESC,document_id DESC,source_locator
    ) latest
    GROUP BY product_id,observed_on,presentation_key,quantity,source_unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
      AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
  ), excluded_city_alias_rows AS MATERIALIZED (
    SELECT witness.document_id,witness.source_locator
    FROM city_alias_witnesses witness JOIN city_alias_conflicts conflict
      ON conflict.product_id=witness.product_id AND conflict.observed_on=witness.observed_on
      AND conflict.presentation_key=witness.presentation_key AND conflict.quantity=witness.quantity
      AND conflict.source_unit_key=witness.source_unit_key
      AND conflict.unit=witness.unit AND conflict.round=witness.round
  )`;
}

function cityConflictJoin(market: string) {
  return `LEFT JOIN excluded_city_alias_rows conflict
    ON ${market}.municipality_id='11001' AND ${market}.name IN ${CITY_ALIAS_NAMES_SQL}
    AND conflict.document_id=r.document_id AND conflict.source_locator=r.source_locator`;
}

function regionalWindow(dateWindow: string) {
  return dateWindow.replace(/\bobserved_on\b/g, "r.observed_on");
}

export function marketsQuery(dateWindow: string) {
  return `WITH ${cityAliasConflicts(dateWindow)}, identities AS (
    SELECT o.product_id,o.market_id,o.observed_on FROM published_price_observation o
    JOIN product p ON p.id=o.product_id WHERE ${dateWindow}
    UNION ALL
    SELECT coalesce(c.corrected_product_id,r.product_id) AS product_id,${cityMarketIdSql()} AS market_id,r.observed_on
    FROM published_regional_price r
    LEFT JOIN regional_price_product_correction c
      ON c.document_id=r.document_id AND c.source_locator=r.source_locator
    JOIN market m ON ${cityMarketJoinSql()} JOIN source_document d ON d.id=r.document_id
    ${cityConflictJoin("m")}
    WHERE ${regionalWindow(dateWindow)} AND conflict.document_id IS NULL
  ), product_dates AS (
    SELECT market_id,product_id,max(observed_on) AS date FROM identities
    GROUP BY market_id,product_id
  )
  SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
  FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
  LEFT JOIN (
    SELECT market_id,count(product_id) AS product_count,max(date) AS date
    FROM product_dates GROUP BY market_id
  ) p ON p.market_id=m.id
  LEFT JOIN LATERAL (
    SELECT observed_on AS supply_date FROM supply_observation
    WHERE market_id=m.id AND ${dateWindow}
    ORDER BY observed_on DESC LIMIT 1
  ) s ON true
  WHERE p.market_id IS NOT NULL OR s.supply_date IS NOT NULL
  ORDER BY product_count DESC,m.name`;
}

/** One market's identity totals do not require loading all market quote payloads. */
export function marketDetailQuery(dateWindow: string) {
  return `WITH ${cityAliasConflicts(dateWindow)}
    SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN LATERAL (
      SELECT count(DISTINCT product_id) AS product_count,max(observed_on) AS date
      FROM (
        SELECT o.product_id,o.observed_on FROM published_price_observation o
        JOIN product p ON p.id=o.product_id WHERE o.market_id=m.id AND ${dateWindow}
        UNION ALL
        SELECT coalesce(c.corrected_product_id,r.product_id) AS product_id,r.observed_on
        FROM published_regional_price r
        LEFT JOIN regional_price_product_correction c
          ON c.document_id=r.document_id AND c.source_locator=r.source_locator
        JOIN source_document d ON d.id=r.document_id
        JOIN market source_market ON ${cityMarketJoinSql("r","source_market")}
        ${cityConflictJoin("source_market")}
        WHERE ${cityMarketNamesForIdSql(cityMarketIdSql("m"))} AND ${regionalWindow(dateWindow)}
          AND conflict.document_id IS NULL
      ) identities
    ) p ON true
    LEFT JOIN LATERAL (
      SELECT max(observed_on) AS supply_date FROM supply_observation
      WHERE market_id=m.id AND ${dateWindow}
    ) s ON true
    WHERE m.id=$1 AND (p.date IS NOT NULL OR s.supply_date IS NOT NULL)`;
}

/** Select eligible winner keys before fetching their wider price/source payloads. */
export function marketProductsQuery(dateWindow: string) {
  return `WITH winners AS MATERIALIZED (
    SELECT DISTINCT ON(product_id) product_id,market_id,source_id,observed_on,period,unit
    FROM published_price_observation WHERE market_id=$1 AND ${dateWindow}
    ORDER BY product_id,observed_on DESC
  )
  SELECT p.*,o.price,o.observed_on AS date,o.unit,o.period,o.document_id,o.source_locator,
    NULL AS previous_price,1 AS market_count,
    CASE WHEN o.source_id='fnc' THEN 'FNC' ELSE 'DANE · SIPSA' END AS source
  FROM winners w JOIN price_observation o
    ON o.product_id=w.product_id AND o.market_id=w.market_id AND o.source_id=w.source_id
    AND o.observed_on=w.observed_on AND o.period=w.period AND o.unit=w.unit
  JOIN product p ON p.id=o.product_id ORDER BY p.id`;
}
