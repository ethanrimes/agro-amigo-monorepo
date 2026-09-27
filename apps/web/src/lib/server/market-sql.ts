/** Count identities before loading any quote payload, package or classification. */
export function marketsQuery(dateWindow: string) {
  return `WITH identities AS (
    SELECT o.product_id,o.market_id,o.observed_on FROM published_price_observation o
    JOIN product p ON p.id=o.product_id WHERE ${dateWindow}
    UNION ALL
    SELECT r.product_id,m.id AS market_id,r.observed_on FROM regional_price r
    JOIN market m ON m.name=r.market_name JOIN source_document d ON d.id=r.document_id
    WHERE ${dateWindow}
  )
  SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
  FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
  LEFT JOIN (
    SELECT market_id,count(DISTINCT product_id) AS product_count,max(observed_on) AS date
    FROM identities GROUP BY market_id
  ) p ON p.market_id=m.id
  LEFT JOIN (
    SELECT market_id,max(observed_on) AS supply_date FROM supply_observation
    WHERE ${dateWindow} GROUP BY market_id
  ) s ON s.market_id=m.id
  WHERE p.market_id IS NOT NULL OR s.market_id IS NOT NULL
  ORDER BY product_count DESC,m.name`;
}

/** One market's identity totals do not require loading all market quote payloads. */
export function marketDetailQuery(dateWindow: string) {
  return `SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN LATERAL (
      SELECT count(DISTINCT product_id) AS product_count,max(observed_on) AS date
      FROM (
        SELECT o.product_id,o.observed_on FROM published_price_observation o
        JOIN product p ON p.id=o.product_id WHERE o.market_id=m.id AND ${dateWindow}
        UNION ALL
        SELECT r.product_id,r.observed_on FROM regional_price r
        JOIN source_document d ON d.id=r.document_id
        WHERE r.market_name=m.name AND ${dateWindow}
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
