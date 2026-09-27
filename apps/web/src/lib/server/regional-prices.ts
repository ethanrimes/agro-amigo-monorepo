import "server-only";
import { database } from "./db";
import { snapshotCache } from "./snapshot-cache";

const latestSnapshot = snapshotCache<Record<string, unknown>[]>(5 * 60 * 1000, 1);

/** Uses regional_market_latest; includes literal market names without a curated
 * market match and keeps the same dated package/round/revision selection. */
export const LATEST_REGIONAL_PRICES_SQL = `
  WITH RECURSIVE names(market_name) AS (
    (SELECT market_name FROM regional_price ORDER BY market_name LIMIT 1)
    UNION ALL
    SELECT n.market_name FROM names prior CROSS JOIN LATERAL (
      SELECT market_name FROM regional_price WHERE market_name>prior.market_name
      ORDER BY market_name LIMIT 1
    ) n
  ), latest AS MATERIALIZED (
    SELECT n.market_name,p.observed_on AS day FROM names n CROSS JOIN LATERAL (
      SELECT observed_on FROM regional_price r WHERE r.market_name=n.market_name
        AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY observed_on DESC LIMIT 1
    ) p
  ), ranked AS (
    SELECT r.*,m.id AS market_id,
      coalesce(c.category_path,string_to_array(r.category,' > ')) AS category_path,
      row_number() OVER(PARTITION BY r.market_name,r.product_name,r.presentation,r.quantity,r.source_unit,r.round
        ORDER BY d.retrieved_at DESC,r.document_id) rn
    FROM regional_price r JOIN latest l ON l.market_name=r.market_name AND l.day=r.observed_on
    JOIN source_document d ON d.id=r.document_id
    LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
    LEFT JOIN market m ON m.name=r.market_name
  ) SELECT * FROM ranked WHERE rn=1 ORDER BY product_name,market_name,quantity,round`;

export function latestRegionalPrices() {
  return latestSnapshot("all", async () => (await database().query(LATEST_REGIONAL_PRICES_SQL)).rows);
}
