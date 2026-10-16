import "server-only";
import { database } from "./db";
import { snapshotCache } from "./snapshot-cache";
import { cityPublicationEpoch } from "./city-publication-epoch";
import { CORABASTOS_CITY_NAMES, CITY_ALIAS_NAMES_SQL, cityMarketIdSql, cityMarketJoinSql, cityMarketNameSql, citySourceMarketIdSql } from "./city-market-alias";
import { verifiedCityCategoryPathSql } from "./category-path-sql";

const latestSnapshot = snapshotCache<Record<string, unknown>[]>(5 * 60 * 1000, 1);
const CITY_ALIAS_NAMES_VALUES_SQL = CORABASTOS_CITY_NAMES
  .map(name => `('${name.replaceAll("'", "''")}')`).join(",");

/** Seek each market's latest report before resolving corrections and provenance.
 * The lateral fence prevents the planner from scanning all historical quotes
 * through resolved_regional_price for the few latest-day rows. Literal market
 * names without a curated match and dated revision selection are retained. */
export const LATEST_REGIONAL_PRICES_SQL = `
  WITH RECURSIVE names(market_name) AS (
    (SELECT market_name FROM published_regional_price ORDER BY market_name LIMIT 1)
    UNION ALL
    SELECT n.market_name FROM names prior CROSS JOIN LATERAL (
      SELECT market_name FROM published_regional_price WHERE market_name>prior.market_name
      ORDER BY market_name LIMIT 1
    ) n
  ), latest AS MATERIALIZED (
    SELECT n.market_name,p.observed_on AS day FROM names n CROSS JOIN LATERAL (
      SELECT observed_on FROM published_regional_price r WHERE r.market_name=n.market_name
        AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY observed_on DESC LIMIT 1
    ) p
  ), dated AS MATERIALIZED (
    SELECT raw.* FROM latest l CROSS JOIN LATERAL (
      SELECT r.* FROM published_regional_price r
      WHERE r.market_name=l.market_name AND r.observed_on=l.day
      OFFSET 0
    ) raw
  ), alias_days AS MATERIALIZED (
    SELECT DISTINCT l.day FROM latest l WHERE l.market_name IN ${CITY_ALIAS_NAMES_SQL}
  ), alias_names(market_name) AS MATERIALIZED (
    SELECT DISTINCT alias_name FROM (VALUES ${CITY_ALIAS_NAMES_VALUES_SQL}) AS names(alias_name)
  ), alias_rival_raw AS MATERIALIZED (
    SELECT rival.* FROM alias_days day CROSS JOIN alias_names name
    CROSS JOIN LATERAL (
      SELECT p.* FROM published_regional_price p
      WHERE p.market_name=name.market_name AND p.observed_on=day.day
      OFFSET 0
    ) rival
  ), alias_latest AS MATERIALIZED (
    SELECT DISTINCT ON (rival.observed_on,coalesce(rival_c.corrected_product_id,rival.product_id),
      lower(btrim(rival.presentation)),rival.quantity,lower(btrim(rival.source_unit)),rival.unit,rival.round,rival.market_name)
      rival.observed_on,coalesce(rival_c.corrected_product_id,rival.product_id) AS effective_product_id,
      lower(btrim(rival.presentation)) AS presentation_key,rival.quantity,
      lower(btrim(rival.source_unit)) AS source_unit_key,rival.unit,rival.round,rival.market_name,
      rival.min_price,rival.max_price,
      (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
      (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
      ${verifiedCityCategoryPathSql("alias_overlay","alias_class.category_path","rival")} AS category_path
    FROM alias_rival_raw rival
    JOIN source_document rival_d ON rival_d.id=rival.document_id
    LEFT JOIN regional_classification alias_class
      ON alias_class.document_id=rival.document_id AND alias_class.source_locator=rival.source_locator
    LEFT JOIN verified_regional_category_overlay alias_overlay
      ON alias_overlay.document_id=rival.document_id AND alias_overlay.source_locator=rival.source_locator
    LEFT JOIN regional_price_product_correction rival_c
      ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
    WHERE rival.market_name IN ${CITY_ALIAS_NAMES_SQL}
    ORDER BY rival.observed_on,coalesce(rival_c.corrected_product_id,rival.product_id),
      lower(btrim(rival.presentation)),rival.quantity,lower(btrim(rival.source_unit)),rival.unit,rival.round,
      rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
  ), alias_conflicts AS MATERIALIZED (
    SELECT observed_on,effective_product_id,presentation_key,quantity,source_unit_key,unit,round
    FROM alias_latest
    GROUP BY observed_on,effective_product_id,presentation_key,quantity,source_unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
      AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
  ), ranked AS (
    SELECT r.document_id,r.source_locator,r.observed_on,
      coalesce(c.corrected_product_id,r.product_id) AS product_id,
      coalesce(c.corrected_product_name,r.product_name) AS product_name,
      r.market_name,coalesce(${cityMarketNameSql()},r.market_name) AS display_market_name,
      coalesce(category_overlay.corrected_category,r.category) AS category,
      r.presentation,r.quantity,r.source_unit,
      r.round,r.round_label,r.min_price,r.max_price,r.unit,
      r.min_unit_price,r.max_unit_price,r.source_page,${cityMarketIdSql()} AS market_id,${citySourceMarketIdSql()} AS source_market_id,
      m.region AS market_region,
      coalesce(string_to_array(category_overlay.corrected_category,' > '),
        cl.category_path,string_to_array(r.category,' > ')) AS category_path,
      row_number() OVER(PARTITION BY ${cityMarketIdSql()},coalesce(c.corrected_product_name,r.product_name),
        r.presentation,r.quantity,r.source_unit,r.round
        ORDER BY r.observed_on DESC,d.retrieved_at DESC,r.document_id) rn
    FROM dated r JOIN source_document d ON d.id=r.document_id
    LEFT JOIN regional_price_product_correction c
      ON c.document_id=r.document_id AND c.source_locator=r.source_locator
    LEFT JOIN regional_classification cl
      ON cl.document_id=r.document_id AND cl.source_locator=r.source_locator
    LEFT JOIN verified_regional_category_overlay category_overlay
      ON category_overlay.document_id=r.document_id
      AND category_overlay.source_locator=r.source_locator
    LEFT JOIN market m ON ${cityMarketJoinSql()}
    WHERE NOT coalesce((m.municipality_id='11001' AND m.name IN ${CITY_ALIAS_NAMES_SQL}
      AND EXISTS (SELECT 1 FROM alias_conflicts conflict
        WHERE conflict.observed_on=r.observed_on
          AND conflict.effective_product_id=coalesce(c.corrected_product_id,r.product_id)
          AND conflict.presentation_key=lower(btrim(r.presentation))
          AND conflict.quantity=r.quantity
          AND conflict.source_unit_key=lower(btrim(r.source_unit))
          AND conflict.unit=r.unit AND conflict.round=r.round)),false)
  ) SELECT * FROM ranked WHERE rn=1 ORDER BY product_name,market_name,quantity,round`;

export async function latestRegionalPrices() {
  for (let attempt = 0; attempt < 2; attempt++) {
    const epoch = await cityPublicationEpoch();
    const rows = await latestSnapshot(epoch, async () => (await database().query(LATEST_REGIONAL_PRICES_SQL)).rows);
    if (epoch === await cityPublicationEpoch()) return rows;
  }
  throw new Error("CITY_PUBLICATION_CHANGED_DURING_READ");
}
