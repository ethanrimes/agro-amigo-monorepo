import "server-only";
import type { PoolClient, QueryResultRow } from "pg";
import { defaultProductPackage } from "../product-filter-defaults";
import { cityFilterUnitsSql, cityDatedIdentityUnitSql, cityComparisonUnitSql, incomingCityPackageUnits } from "./city-package-equivalence";
import { currentClassifications } from "../price-classification";
import { normalizeLabel, normalizeOfficialLabels } from "../label-normalization";
import { database, WINDOW } from "./db";
import { summaryReferencesForProduct } from "./summary-references";
import { withProductDetailStage } from "./product-detail-diagnostics";
import { resolveMarketAlias } from "./market-alias";
import { CITY_ALIAS_NAMES_SQL, CORABASTOS_CITY_MARKET_ID, cityCrossAliasConflictSql, cityMarketIdSql, cityMarketJoinSql, cityMarketNameSql, citySourceMarketIdSql, resolveCityMarketId } from "./city-market-alias";
import { verifiedCityCategoryPathSql } from "./category-path-sql";

/** Shared quote identities for product filters, maps and market comparisons.
 * City prices are per original package; monthly references keep their base unit.
 * Latest round / publisher revision wins within the same dated quote identity.
 */
// A raw-source superset proves when no two Corabastos literals can conflict
// for this product. The gate and selected quotes execute in one SQL snapshot;
// a concurrent publication cannot invalidate a separate options read.
function selectedOrdinaryScopeCtes(recent: boolean, allPackages = false) { const dateScope = recent ? "AND r.observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date AND r.observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date" : "";
const packageScope = allPackages ? "" : `AND lower(btrim(r.presentation))=lower(btrim($4))
   AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5`;
return `WITH ordinary_market_names AS MATERIALIZED (
 SELECT name FROM market WHERE id=ANY($7::text[]) AND id<>'sipsa-bogota-d-c-corabastos'
), ordinary_keys AS MATERIALIZED (
 SELECT r.*,r.product_id AS effective_product_id,r.product_name AS effective_product_name FROM regional_price r
 WHERE r.product_id=$1 AND r.market_name IN (SELECT name FROM ordinary_market_names)
   ${packageScope}
   ${dateScope}
   AND NOT EXISTS (SELECT 1 FROM regional_price_product_correction c
     WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
 UNION ALL
 SELECT r.*,c.corrected_product_id AS effective_product_id,c.corrected_product_name AS effective_product_name
 FROM regional_price_product_correction c
 JOIN regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
 WHERE c.corrected_product_id=$1 AND r.market_name IN (SELECT name FROM ordinary_market_names)
   ${packageScope}
   ${dateScope}
), ordinary_eligible_docs AS MATERIALIZED (
 SELECT DISTINCT k.document_id FROM ordinary_keys k
 WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict c
   WHERE c.document_id=k.document_id)
   AND EXISTS (SELECT 1 FROM published_regional_price accepted
     WHERE accepted.document_id=k.document_id OFFSET 0)
), ordinary_scoped AS MATERIALIZED (
 SELECT k.document_id,k.source_locator,k.observed_on,
  k.effective_product_id AS product_id,k.effective_product_name AS product_name,
  k.market_name,k.category,k.presentation,k.quantity,k.source_unit,k.round,k.round_label,
  k.min_price,k.max_price,k.unit,k.min_unit_price,k.max_unit_price,k.source_page
 FROM ordinary_keys k JOIN ordinary_eligible_docs e ON e.document_id=k.document_id
) `; }

const SELECTED_ORDINARY_VIEW_ELIGIBILITY = `AND EXISTS (SELECT 1 FROM published_regional_price accepted
     WHERE accepted.document_id=k.document_id OFFSET 0)`;

function selectedOrdinary078Sql(sql: string): string {
  const directEligibility = FILTER_OPTIONS_078_DIRECT_ELIGIBILITY.replaceAll("key.document_id", "k.document_id");
  if (sql.split(SELECTED_ORDINARY_VIEW_ELIGIBILITY).length !== 2)
    throw new Error("SELECTED_ORDINARY_078_ELIGIBILITY_ANCHOR_MISMATCH");
  return sql.replace(SELECTED_ORDINARY_VIEW_ELIGIBILITY, directEligibility);
}

async function guardedOrdinarySql(
  client: PoolClient, sql: string,
) {
  await client.query("LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE");
  const view = (await client.query<{ definition_sha256: string | null }>(FILTER_OPTIONS_VIEW_HASH_SQL)).rows[0];
  return view?.definition_sha256 === PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256
    ? selectedOrdinary078Sql(sql)
    : sql;
}

async function selectedOrdinarySnapshotQuery<T extends QueryResultRow>(
  db: ReturnType<typeof database>, sql: string, args: (string | string[])[],
): Promise<{ rows: T[] }> {
  const client = await db.connect();
  let transactionStarted = false;
  try {
    await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
    transactionStarted = true;
    const guardedSql = await guardedOrdinarySql(client, sql);
    const result = await client.query<T>(guardedSql, args);
    await client.query("COMMIT");
    transactionStarted = false;
    return result;
  } catch (error) {
    if (transactionStarted) await client.query("ROLLBACK").catch(() => {});
    throw error;
  } finally {
    client.release();
  }
}

// On the package path, marker rows propagate the view's document-wide eligibility
// once per document instead of joining every source locator to its gate row.
function selectedAliasOverlapCtes(packageScoped = false) {
const packageScope = packageScoped ? `\n      AND lower(btrim(rival.presentation))=lower(btrim($4))
      AND upper(left(rival.presentation,1)) || lower(substr(rival.presentation,2))=$4
      AND rival.quantity::float8::text || ' ' || upper(left(rival.source_unit,1)) || lower(substr(rival.source_unit,2))=$5` : "";
return `WITH alias_keys AS MATERIALIZED (
    SELECT rival.document_id,rival.source_locator,rival.observed_on,lower(btrim(rival.presentation)) AS presentation_key,
      rival.quantity,lower(btrim(rival.source_unit)) AS unit_key,rival.unit,rival.round,rival.market_name
    FROM regional_price rival
    LEFT JOIN regional_price_product_correction rival_c
      ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
    WHERE rival.product_id=$1 AND rival_c.document_id IS NULL
      AND rival.market_name IN ${CITY_ALIAS_NAMES_SQL}${packageScope}
    UNION ALL
    SELECT rival.document_id,rival.source_locator,rival.observed_on,lower(btrim(rival.presentation)),rival.quantity,
      lower(btrim(rival.source_unit)),rival.unit,rival.round,rival.market_name
    FROM regional_price_product_correction rival_c
    JOIN regional_price rival ON rival.document_id=rival_c.document_id
      AND rival.source_locator=rival_c.source_locator
    WHERE rival_c.corrected_product_id=$1
      AND rival.market_name IN ${CITY_ALIAS_NAMES_SQL}${packageScope}
  ), ${packageScoped ? "" : `alias_overlap AS MATERIALIZED (
    SELECT 1 FROM alias_keys
    GROUP BY observed_on,presentation_key,quantity,unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
    LIMIT 1
  ), `}alias_source_ids AS MATERIALIZED (
    SELECT DISTINCT document_id,source_locator FROM alias_keys
  ), alias_document_samples AS MATERIALIZED (
    SELECT document_id,min(source_locator) AS sample_locator
    FROM alias_source_ids GROUP BY document_id
  ), alias_eligible_documents AS MATERIALIZED (
    SELECT sample.document_id FROM alias_document_samples sample
    CROSS JOIN LATERAL (
      -- The published view is the authoritative quarantine/adjudication gate.
      -- Its rule is document-wide, so one retained candidate row proves it.
      SELECT 1 FROM published_regional_price published
      WHERE published.document_id=sample.document_id
        AND published.source_locator=sample.sample_locator OFFSET 0
    ) eligible
  )${packageScoped ? `, alias_eligibility_markers AS MATERIALIZED (
    SELECT document_id,source_locator,FALSE AS document_is_eligible FROM alias_source_ids
    UNION ALL
    SELECT document_id,NULL::text AS source_locator,TRUE AS document_is_eligible FROM alias_eligible_documents
  ), alias_eligible_source_ids AS MATERIALIZED (
    SELECT document_id,source_locator
    FROM (
      SELECT document_id,source_locator,
        bool_or(document_is_eligible) OVER (PARTITION BY document_id) AS document_is_eligible
      FROM alias_eligibility_markers
    ) propagated
    WHERE document_is_eligible AND source_locator IS NOT NULL
  )` : ``}, alias_scoped AS MATERIALIZED (
    SELECT r.document_id,r.source_locator,r.observed_on,
      CASE WHEN c.document_id IS NULL THEN r.product_id ELSE c.corrected_product_id END AS product_id,
      CASE WHEN c.document_id IS NULL THEN r.product_name ELSE c.corrected_product_name END AS product_name,
      r.market_name,coalesce(o.corrected_category,r.category) AS category,
      r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
      r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
    FROM ${packageScoped ? "alias_eligible_source_ids source_id" : "alias_source_ids source_id\n    JOIN alias_eligible_documents eligible ON eligible.document_id=source_id.document_id"}
    JOIN regional_price r ON r.document_id=source_id.document_id
      AND r.source_locator=source_id.source_locator
    LEFT JOIN regional_price_product_correction c ON c.document_id=r.document_id
      AND c.source_locator=r.source_locator
    LEFT JOIN verified_regional_category_overlay o ON o.document_id=r.document_id
      AND o.source_locator=r.source_locator
  )${packageScoped ? `, alias_target_identities AS MATERIALIZED (
    SELECT DISTINCT product_id,observed_on,lower(btrim(presentation)) AS presentation_key,
      quantity,lower(btrim(source_unit)) AS unit_key,unit,round
    FROM alias_scoped
  ), alias_target_packages AS MATERIALIZED (
    SELECT DISTINCT product_id,presentation_key,quantity,unit_key,unit
    FROM alias_target_identities
  ), alias_conflict_source_keys AS MATERIALIZED (
    SELECT package.product_id,package.presentation_key,package.quantity,package.unit_key,package.unit,
      raw.observed_on,raw.round,raw.document_id,raw.source_locator
    FROM alias_target_packages package
    JOIN regional_price raw ON raw.product_id=package.product_id
      AND lower(btrim(raw.presentation))=package.presentation_key
      AND raw.quantity=package.quantity
      AND lower(btrim(raw.source_unit))=package.unit_key AND raw.unit=package.unit
    WHERE raw.market_name IN ${CITY_ALIAS_NAMES_SQL}
      AND NOT EXISTS (SELECT 1 FROM regional_price_product_correction corrected
        WHERE corrected.document_id=raw.document_id AND corrected.source_locator=raw.source_locator)
    UNION ALL
    SELECT package.product_id,package.presentation_key,package.quantity,package.unit_key,package.unit,
      raw.observed_on,raw.round,raw.document_id,raw.source_locator
    FROM alias_target_packages package
    JOIN regional_price_product_correction corrected
      ON corrected.corrected_product_id=package.product_id
    JOIN regional_price raw ON raw.document_id=corrected.document_id
      AND raw.source_locator=corrected.source_locator
      AND lower(btrim(raw.presentation))=package.presentation_key
      AND raw.quantity=package.quantity
      AND lower(btrim(raw.source_unit))=package.unit_key AND raw.unit=package.unit
    WHERE raw.market_name IN ${CITY_ALIAS_NAMES_SQL}
  ), alias_published_candidates AS MATERIALIZED (
    SELECT key.product_id,key.presentation_key,key.quantity,key.unit_key,key.unit,
      published.observed_on,published.round,published.market_name,published.document_id,published.source_locator,
      source.retrieved_at,published.min_price,published.max_price,
      published.min_unit_price,published.max_unit_price,
      ${verifiedCityCategoryPathSql('category_overlay','classification.category_path','raw')} AS category_path
    FROM alias_conflict_source_keys key
    JOIN published_regional_price published
      ON published.document_id=key.document_id AND published.source_locator=key.source_locator
    JOIN regional_price raw ON raw.document_id=published.document_id
      AND raw.source_locator=published.source_locator
    JOIN source_document source ON source.id=published.document_id
    LEFT JOIN regional_classification classification
      ON classification.document_id=published.document_id
      AND classification.source_locator=published.source_locator
    LEFT JOIN verified_regional_category_overlay category_overlay
      ON category_overlay.document_id=published.document_id
      AND category_overlay.source_locator=published.source_locator
  ), alias_conflict_latest AS MATERIALIZED (
    SELECT DISTINCT ON (target.product_id,target.observed_on,target.presentation_key,
                        target.quantity,target.unit_key,target.unit,target.round,rival.market_name)
      target.product_id,target.observed_on,target.presentation_key,target.quantity,target.unit_key,
      target.unit,target.round,rival.market_name,rival.min_price,rival.max_price,
      rival.min_unit_price,rival.max_unit_price,rival.category_path,rival.retrieved_at,
      rival.document_id,rival.source_locator
    FROM alias_target_identities target
    JOIN alias_published_candidates rival
      ON rival.product_id=target.product_id
      AND rival.presentation_key=target.presentation_key
      AND rival.quantity=target.quantity AND rival.unit_key=target.unit_key
      AND rival.unit=target.unit AND rival.observed_on=target.observed_on
      AND rival.round=target.round
    ORDER BY target.product_id,target.observed_on,target.presentation_key,target.quantity,
      target.unit_key,target.unit,target.round,rival.market_name,
      rival.retrieved_at DESC,rival.document_id DESC,rival.source_locator
  ), alias_conflicts AS MATERIALIZED (
    SELECT product_id,observed_on,presentation_key,quantity,unit_key,unit,round
    FROM alias_conflict_latest
    GROUP BY product_id,observed_on,presentation_key,quantity,unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
       AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
  ), alias_market_scope AS MATERIALIZED (
    SELECT m.* FROM market m
    WHERE m.municipality_id='11001' AND m.name IN ${CITY_ALIAS_NAMES_SQL}
  )` : ``} `; }


export function cityPriceQuotes(classify: boolean, marketNameFilter = "", guardAliasOverlap = false, ordinaryScoped = false, precomputedAliasConflicts = false, packageScopedAliasGate = false) { return `
  SELECT product_id,market_id,source_market_id,market_name,city,region,product_name,${ordinaryScoped ? "coalesce(overlay.corrected_category,category) AS category,coalesce(string_to_array(overlay.corrected_category,' > '),category_path) AS category_path" : "category,category_path"},
    observed_on,(coalesce(money.corrected_min_price,city.min_price)+coalesce(money.corrected_max_price,city.max_price))/2 AS price,
    coalesce(money.corrected_min_price,city.min_price) AS min_price,
    coalesce(money.corrected_max_price,city.max_price) AS max_price,
    comparison_unit AS unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,city.document_id,city.source_locator,source_url,'daily'::text AS period,source_page,source_units FROM (
    ${guardAliasOverlap ? selectedAliasOverlapCtes(packageScopedAliasGate) : ""}
    SELECT DISTINCT ON(r.product_id,${cityMarketIdSql()},r.observed_on,lower(btrim(r.presentation)),r.quantity,${cityDatedIdentityUnitSql()})
      r.*,${cityComparisonUnitSql()} AS comparison_unit,r.quantity::float8::text || ' ' || r.source_unit AS source_units,${cityMarketIdSql()} AS market_id,${citySourceMarketIdSql()} AS source_market_id,m.city,m.region,
      ${verifiedCityCategoryPathSql("path_overlay", classify ? "c.category_path" : "NULL::text[]", "r")} AS category_path,
      ${cityFilterUnitsSql()} AS units,d.source_url
    FROM ${guardAliasOverlap ? "alias_scoped" : ordinaryScoped ? "ordinary_scoped" : "resolved_regional_price"} r JOIN ${guardAliasOverlap && packageScopedAliasGate ? "alias_market_scope" : "market"} m ON ${cityMarketJoinSql()}
    JOIN source_document d ON d.id=r.document_id
    ${classify ? "LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator" : ""}
    LEFT JOIN verified_regional_category_overlay path_overlay ON path_overlay.document_id=r.document_id AND path_overlay.source_locator=r.source_locator
    ${marketNameFilter}
    ${marketNameFilter ? "AND" : "WHERE"} ${guardAliasOverlap
      ? packageScopedAliasGate
        ? `NOT EXISTS (SELECT 1 FROM alias_conflicts conflict
            WHERE conflict.product_id=r.product_id AND conflict.observed_on=r.observed_on
              AND conflict.presentation_key=lower(btrim(r.presentation))
              AND conflict.quantity=r.quantity AND conflict.unit_key=lower(btrim(r.source_unit))
              AND conflict.unit=r.unit AND conflict.round=r.round)`
        : `CASE WHEN EXISTS(SELECT 1 FROM alias_overlap) THEN NOT ${cityCrossAliasConflictSql()} ELSE TRUE END`
      : precomputedAliasConflicts
        ? `NOT EXISTS (SELECT 1 FROM excluded_city_alias_rows conflict
             WHERE conflict.document_id=r.document_id AND conflict.source_locator=r.source_locator)`
        : `NOT ${cityCrossAliasConflictSql()}`}
    AND EXISTS (SELECT 1 FROM published_regional_price accepted
      WHERE accepted.document_id=r.document_id
        AND accepted.source_locator=r.source_locator OFFSET 0)
    ORDER BY r.product_id,${cityMarketIdSql()},r.observed_on,lower(btrim(r.presentation)),r.quantity,${cityDatedIdentityUnitSql()},r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city${ordinaryScoped ? " LEFT JOIN LATERAL (SELECT corrected_category FROM verified_regional_category_overlay vo WHERE vo.document_id=city.document_id AND vo.source_locator=city.source_locator OFFSET 0) overlay ON true" : ""}
  LEFT JOIN verified_city_pdf_price_overlay money ON money.document_id=city.document_id
    AND money.source_locator=city.source_locator`; }
export const CITY_PRICE_QUOTES = cityPriceQuotes(true);

function priceQuotes(city: string, monthlyFilter = "") { return `
  SELECT o.product_id,m.id AS market_id,m.id AS source_market_id,m.name AS market_name,m.city,m.region,
    p.name AS product_name,p.category,ARRAY[p.category]::text[] AS category_path,
    o.observed_on,o.price,o.min_price,o.max_price,o.unit,
    'Por unidad de medida'::text AS presentation,
    CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
    CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
    o.document_id,o.source_locator,o.source_url,o.period,
    coalesce(substring(o.source_locator from '^PDF page ([1-9][0-9]{0,4})(?:[[:space:],;]|$)')::integer,1) AS source_page,
    NULL::text AS source_units
  FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
  ${monthlyFilter}
  UNION ALL
${city}`; }
// A municipality name can occur in multiple departments. Clarify the
// selector label for farm/mill series without changing the market identity.
function ordinaryMarketOptionNameSql(series: string, name: string, region: string) {
  return `CASE WHEN ${series} IN ('farmgate','mill') AND nullif(btrim(${region}),'') IS NOT NULL
    THEN ${name} || ' · ' || ${region} ELSE ${name} END`;
}
export const PRICE_QUOTES = priceQuotes(CITY_PRICE_QUOTES);
// Dates, prices and revision winners do not depend on classification metadata.
// Fetch that metadata only for the selected display rows, not each historical
// observation feeding an aggregate or a picker.
export const PRICE_QUOTE_VALUES = priceQuotes(cityPriceQuotes(false));
const FILTER_REGION_SQL = (region: string) => `($2='' OR translate(lower(btrim(${region})), 'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))`;
// The ambiguity fallback needs the same dated winners as PRICE_QUOTE_VALUES,
// but only for the requested product/region. Push those exact dimensions into
// each source arm before DISTINCT ON; the outer projection still applies the
// same date cutoff and option grouping as the legacy fallback.
export const PRODUCT_FILTER_OPTIONS_AMBIGUOUS_QUOTES_SQL = `
  WITH quotes AS (${priceQuotes(
    cityPriceQuotes(false, `WHERE r.product_id=$1 AND ${FILTER_REGION_SQL("m.region")}`),
    `WHERE o.product_id=$1 AND ${FILTER_REGION_SQL("m.region")}`,
  )})
  SELECT DISTINCT series,market_id,
    ${ordinaryMarketOptionNameSql("series", "market_name", "region")} AS market_name,
    presentation,units,
    min(observed_on) OVER (PARTITION BY series,market_id,presentation,units) AS first_report_on,
    max(observed_on) OVER (PARTITION BY series,market_id,presentation,units) AS last_report_on
  FROM quotes
  WHERE product_id=$1 AND ${FILTER_REGION_SQL("region")}
    AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  ORDER BY series,market_name,presentation,units`;
// National comparisons seek each retained product/package key in the ordered
// city index, then resolve the newest date, round and publisher revision.
// The recent variant applies the same fixed Bogotá-day cutoff at every key
// and winner seek; no user value is interpolated into SQL. Corrections retain
// their own branch and the exact original package and source identity.
export function cityLooseLatestQuotes(recent: boolean) {
const recentDate = recent
  ? " AND r.observed_on > ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date - INTERVAL '12 months')::date"
  : "";
return `
WITH ranked AS MATERIALIZED (
  SELECT requested.product_id,keys.market_name,keys.presentation_key,keys.quantity,
    keys.source_unit_key,keys.unit,quote.observed_on,quote.round,
    quote.document_id,quote.source_locator,1::bigint AS date_round_rank
  FROM unnest($1::text[]) requested(product_id)
  CROSS JOIN LATERAL (
    WITH RECURSIVE raw_keys AS (
      (SELECT r.market_name,lower(btrim(r.presentation)) AS presentation_key,
        r.quantity,lower(btrim(r.source_unit)) AS source_unit_key,r.unit
       FROM published_regional_price r
       WHERE r.product_id=requested.product_id AND r.observed_on<=CURRENT_DATE${recentDate}
       ORDER BY r.market_name,lower(btrim(r.presentation)),r.quantity,
         lower(btrim(r.source_unit)),r.unit LIMIT 1)
      UNION ALL
      SELECT next.* FROM raw_keys previous CROSS JOIN LATERAL (
        SELECT r.market_name,lower(btrim(r.presentation)) AS presentation_key,
          r.quantity,lower(btrim(r.source_unit)) AS source_unit_key,r.unit
        FROM published_regional_price r
        WHERE r.product_id=requested.product_id AND r.observed_on<=CURRENT_DATE${recentDate}
          AND (r.market_name,lower(btrim(r.presentation)),r.quantity,
            lower(btrim(r.source_unit)),r.unit) >
            (previous.market_name,previous.presentation_key,
              previous.quantity,previous.source_unit_key,previous.unit)
        ORDER BY r.market_name,lower(btrim(r.presentation)),r.quantity,
          lower(btrim(r.source_unit)),r.unit LIMIT 1
      ) next
    )
    SELECT * FROM raw_keys
    UNION
    SELECT r.market_name,lower(btrim(r.presentation)),r.quantity,
      lower(btrim(r.source_unit)),r.unit
    FROM regional_price_product_correction c JOIN published_regional_price r
      ON r.document_id=c.document_id AND r.source_locator=c.source_locator
    WHERE c.corrected_product_id=requested.product_id AND r.observed_on<=CURRENT_DATE${recentDate}
  ) keys
  CROSS JOIN LATERAL (
    SELECT * FROM (
      (SELECT r.observed_on,r.round,r.document_id,r.source_locator
       FROM published_regional_price r
       WHERE NOT EXISTS (SELECT 1 FROM regional_price_product_correction c
         WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator OFFSET 0)
         AND r.product_id=requested.product_id AND r.market_name=keys.market_name
         AND lower(btrim(r.presentation))=keys.presentation_key
         AND r.quantity=keys.quantity AND lower(btrim(r.source_unit))=keys.source_unit_key
         AND r.unit=keys.unit AND r.observed_on<=CURRENT_DATE${recentDate}
       ORDER BY r.observed_on DESC,r.round DESC FETCH FIRST 1 ROWS WITH TIES)
      UNION ALL
      (SELECT r.observed_on,r.round,r.document_id,r.source_locator
       FROM regional_price_product_correction c JOIN published_regional_price r
         ON r.document_id=c.document_id AND r.source_locator=c.source_locator
       WHERE c.corrected_product_id=requested.product_id AND r.market_name=keys.market_name
         AND lower(btrim(r.presentation))=keys.presentation_key
         AND r.quantity=keys.quantity AND lower(btrim(r.source_unit))=keys.source_unit_key
         AND r.unit=keys.unit AND r.observed_on<=CURRENT_DATE${recentDate}
       ORDER BY r.observed_on DESC,r.round DESC FETCH FIRST 1 ROWS WITH TIES)
    ) candidates ORDER BY observed_on DESC,round DESC FETCH FIRST 1 ROWS WITH TIES
  ) quote
), dated_revisions AS (
  SELECT DISTINCT ON(k.product_id,${cityMarketIdSql()},k.observed_on,k.presentation_key,k.quantity,k.source_unit_key)
    k.product_id,${cityMarketIdSql()} AS market_id,${citySourceMarketIdSql("raw")} AS source_market_id,raw.market_name,m.city,m.region,
    coalesce(c.corrected_product_name,raw.product_name) AS product_name,
    raw.category,${verifiedCityCategoryPathSql('category_overlay','classification.category_path','raw')} AS category_path,
    k.observed_on,k.round AS winning_round,d.retrieved_at AS retrieved_at,
    (raw.min_price+raw.max_price)/2 AS price,
    raw.min_price,raw.max_price,${cityComparisonUnitSql('raw','d')} AS unit,
    upper(left(raw.presentation,1)) || lower(substr(raw.presentation,2)) AS presentation,
    ${cityFilterUnitsSql('raw','d')} AS units,
    raw.quantity::float8::text || ' ' || raw.source_unit AS source_units,
    'city'::text AS series,raw.document_id,raw.source_locator,d.source_url,
    'daily'::text AS period,raw.source_page
  FROM ranked k JOIN published_regional_price raw
    ON raw.document_id=k.document_id AND raw.source_locator=k.source_locator
  JOIN market m ON ${cityMarketJoinSql("raw")}
  JOIN source_document d ON d.id=raw.document_id
  LEFT JOIN regional_price_product_correction c
    ON c.document_id=raw.document_id AND c.source_locator=raw.source_locator
  LEFT JOIN regional_classification classification
    ON classification.document_id=raw.document_id AND classification.source_locator=raw.source_locator
  LEFT JOIN verified_regional_category_overlay category_overlay
    ON category_overlay.document_id=raw.document_id AND category_overlay.source_locator=raw.source_locator
  WHERE k.date_round_rank=1 AND NOT ${cityCrossAliasConflictSql("raw","m","k.product_id")}
  ORDER BY k.product_id,${cityMarketIdSql()},k.observed_on,k.presentation_key,k.quantity,k.source_unit_key,
    k.round DESC,d.retrieved_at DESC,raw.source_locator
)
SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
  product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
  market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
  price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
FROM dated_revisions
ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,winning_round DESC,retrieved_at DESC,document_id
`;
}
export const CITY_LOOSE_LATEST_QUOTES = cityLooseLatestQuotes(false);
export const CITY_RECENT_LOOSE_LATEST_QUOTES = cityLooseLatestQuotes(true);

// The dated publisher winner is chosen before the outer grouping by unit.
// A rare legacy row can give the same dated package two different `unit`
// values; then the losing unit may have an older surviving dated winner. Seek
// only selected latest rows for that conflict and let the generic dated query
// handle those exact product IDs. Ordinary indexed batches stay unchanged.
export const CITY_LOOSE_UNIT_AMBIGUITY = `
WITH selected(product_id,document_id,source_locator) AS (
  SELECT * FROM unnest($1::text[],$2::text[],$3::text[])
)
SELECT DISTINCT selected.product_id FROM selected
JOIN published_regional_price own ON own.document_id=selected.document_id
  AND own.source_locator=selected.source_locator
WHERE EXISTS (
  SELECT 1 FROM published_regional_price competitor
  WHERE competitor.product_id=selected.product_id
    AND competitor.market_name=own.market_name
    AND competitor.observed_on=own.observed_on
    AND lower(btrim(competitor.presentation))=lower(btrim(own.presentation))
    AND competitor.quantity=own.quantity
    AND lower(btrim(competitor.source_unit))=lower(btrim(own.source_unit))
    AND competitor.unit<>own.unit
    AND NOT EXISTS (SELECT 1 FROM regional_price_product_correction correction
      WHERE correction.document_id=competitor.document_id
        AND correction.source_locator=competitor.source_locator OFFSET 0)
) OR EXISTS (
  SELECT 1 FROM regional_price_product_correction correction
  JOIN published_regional_price competitor ON competitor.document_id=correction.document_id
    AND competitor.source_locator=correction.source_locator
  WHERE correction.corrected_product_id=selected.product_id
    AND competitor.market_name=own.market_name
    AND competitor.observed_on=own.observed_on
    AND lower(btrim(competitor.presentation))=lower(btrim(own.presentation))
    AND competitor.quantity=own.quantity
    AND lower(btrim(competitor.source_unit))=lower(btrim(own.source_unit))
    AND competitor.unit<>own.unit
)`;

// The product detail query already has a curated market name for each market
// ID. Applying it before the dated revision sort lets regional_price_lookup
// seek by both product and market, including during a full-history request.
const PRODUCT_DETAIL_QUOTE_VALUES = priceQuotes(cityPriceQuotes(false,
  "WHERE r.product_id=$1 AND r.market_name=selected_market.name AND m.id=selected_market.id"));
// A single ordinary market can seek every original package revision directly.
// Filtering the requested display package stays after the dated winner sort.
const PRODUCT_DETAIL_QUOTE_SCOPED_VALUES = priceQuotes(cityPriceQuotes(false,
  "WHERE r.product_id=$1 AND r.market_name=selected_market.name AND m.id=selected_market.id", false, true));
const PRODUCT_DETAIL_ALIAS_QUOTE_VALUES = priceQuotes(cityPriceQuotes(false,
  `WHERE r.product_id=$1 AND r.market_name IN ${CITY_ALIAS_NAMES_SQL} AND m.municipality_id='11001'`, true));
// A display predicate can be pushed below the revision sort only when every
// normalized package identity has one spelling. Otherwise it could discard the
// winning revision and expose an older quote under the requested spelling.
const PRODUCT_DETAIL_PACKAGE_VALUES = priceQuotes(cityPriceQuotes(false,
  `WHERE r.product_id=$1 AND r.market_name=selected_market.name AND m.id=selected_market.id
    AND lower(btrim(r.presentation))=lower(btrim($4))
    AND upper(left(r.presentation,1)) || lower(substr(r.presentation,2))=$4
    AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5`));
const PRODUCT_DETAIL_PACKAGE_SCOPED_VALUES = priceQuotes(cityPriceQuotes(false,
  `WHERE r.product_id=$1 AND r.market_name=selected_market.name AND m.id=selected_market.id
    AND lower(btrim(r.presentation))=lower(btrim($4))
    AND upper(left(r.presentation,1)) || lower(substr(r.presentation,2))=$4
    AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5`, false, true));
const PRODUCT_DETAIL_ALIAS_PACKAGE_VALUES = priceQuotes(cityPriceQuotes(false,
  `WHERE r.product_id=$1 AND r.market_name IN ${CITY_ALIAS_NAMES_SQL} AND m.municipality_id='11001'
    AND lower(btrim(r.presentation))=lower(btrim($4))
    AND upper(left(r.presentation,1)) || lower(substr(r.presentation,2))=$4
    AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5`, true, false, false, true));

// Keep each indexed market batch below the SQL deadline; all batches share one snapshot.
const PARTITION_MARKETS = 3;
const MERGE_PARTITIONED_CITY_SQL = `WITH partial AS (
  SELECT (h->>'date')::date AS date,(h->>'price_sum')::numeric AS price_sum,
    (h->>'price_count')::bigint AS price_count,(h->>'market_count')::bigint AS market_count,
    h->'sources' AS sources FROM jsonb_array_elements($1::jsonb) h
), dates AS (
  SELECT date,sum(price_sum)/sum(price_count) AS price,sum(market_count) AS market_count
  FROM partial GROUP BY date
), sources AS (
  SELECT p.date,coalesce(jsonb_agg(DISTINCT src.value) FILTER (WHERE src.value IS NOT NULL),'[]'::jsonb) AS sources
  FROM partial p LEFT JOIN LATERAL jsonb_array_elements(p.sources) src(value) ON true GROUP BY p.date
), history AS (
  SELECT d.date,d.price,d.market_count,s.sources FROM dates d JOIN sources s USING(date)
) SELECT
  (SELECT coalesce(jsonb_agg(m ORDER BY m->>'market_id'),'[]'::jsonb) FROM jsonb_array_elements($2::jsonb) m) AS markets,
  (SELECT coalesce(jsonb_agg(h ORDER BY h.date),'[]'::jsonb) FROM history h) AS history`;

async function partitionedCityQuotes(
  db: ReturnType<typeof database>,sql: string,args: (string | string[])[],marketIds: string[],guard078Eligibility = false,
): Promise<{ rows: { markets: ProductMarketQuote[]; history: ProductHistoryPoint[] }[] }> {
  const canonicalIds = [...new Set(marketIds.map(resolveCityMarketId))];
  const client = await db.connect();
  let transactionStarted = false;
  try {
    await client.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    transactionStarted = true;
    const selectedSql = guard078Eligibility ? await guardedOrdinarySql(client, sql) : sql;
    const markets: ProductMarketQuote[] = [];
    const history: Array<ProductHistoryPoint & { price_sum: string; price_count: number }> = [];
    const seenMarkets = new Set<string>();
    for (let offset = 0; offset < canonicalIds.length; offset += PARTITION_MARKETS) {
      const chunk = canonicalIds.slice(offset,offset + PARTITION_MARKETS);
      const result = await client.query<{ markets: ProductMarketQuote[]; history: typeof history }>(
        selectedSql,[...args.slice(0,6),chunk],
      );
      const row = result.rows[0];
      if (!row) throw new Error('CITY_HISTORY_CHUNK_EMPTY');
      for (const market of row.markets) {
        if (!chunk.includes(market.market_id) || seenMarkets.has(market.market_id))
          throw new Error('CITY_HISTORY_CHUNK_MARKET_OVERLAP');
        seenMarkets.add(market.market_id);
        markets.push(market);
      }
      history.push(...row.history);
    }
    const result = await client.query<{ markets: ProductMarketQuote[]; history: ProductHistoryPoint[] }>(
      MERGE_PARTITIONED_CITY_SQL,[JSON.stringify(history),JSON.stringify(markets)],
    );
    if (!result.rows[0]) throw new Error('CITY_HISTORY_MERGE_EMPTY');
    await client.query('COMMIT');
    transactionStarted = false;
    return { rows: [result.rows[0]] };
  } catch (error) {
    if (transactionStarted) await client.query('ROLLBACK').catch(() => {});
    throw error;
  } finally {
    client.release();
  }
}

export async function withQuoteClassifications<T extends {
  series: string; document_id: string; source_locator: string; category_path: string[];
}>(rows: T[]): Promise<T[]> {
  const city = rows.filter((row) => row.series === "city");
  if (!city.length) return rows;
  const paths = (await database().query(`
    SELECT selected.document_id,selected.source_locator,
      ${verifiedCityCategoryPathSql('o','c.category_path','raw')} AS category_path
    FROM (SELECT DISTINCT document_id,source_locator FROM unnest($1::text[],$2::text[]) AS input(document_id,source_locator)) selected
    JOIN published_regional_price accepted
      ON accepted.document_id=selected.document_id AND accepted.source_locator=selected.source_locator
    LEFT JOIN verified_regional_category_overlay o
      ON o.document_id=selected.document_id AND o.source_locator=selected.source_locator
    LEFT JOIN regional_classification c
      ON c.document_id=selected.document_id AND c.source_locator=selected.source_locator
    LEFT JOIN regional_price raw
      ON raw.document_id=selected.document_id AND raw.source_locator=selected.source_locator`, [city.map((row) => row.document_id), city.map((row) => row.source_locator)])).rows;
  const bySource = new Map(paths.map((row) => [JSON.stringify([row.document_id, row.source_locator]), row.category_path]));
  return rows.map((row) => ({ ...row, category_path: row.series === "city"
    ? bySource.get(JSON.stringify([row.document_id, row.source_locator])) || row.category_path
    : row.category_path }));
}

/** Filter availability depends on retained dimensions, not dated price winners.
 * Ordinary parser output normalizes case; differing whitespace spellings of the
 * same quote dimension are rare and retain the exact revision-aware fallback.
 */
// Seek only covered package keys for this product. Publication holdbacks are
// document-wide; check each covered original once, then fetch money and
// classification facts only for keys shared by different literal aliases.
export const PRODUCT_FILTER_OPTIONS_SQL = `
  WITH raw_keys AS MATERIALIZED (
    SELECT r.document_id,r.source_locator,r.observed_on,r.product_id AS effective_product_id,
      r.market_name,r.presentation,r.quantity,r.source_unit,r.unit,r.round
    FROM regional_price r
    WHERE r.product_id=$1 AND NOT EXISTS (
      SELECT 1 FROM regional_price_product_correction c
      WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
    UNION ALL
    SELECT r.document_id,r.source_locator,r.observed_on,c.corrected_product_id AS effective_product_id,
      r.market_name,r.presentation,r.quantity,r.source_unit,r.unit,r.round
    FROM regional_price_product_correction c
    JOIN regional_price r ON r.document_id=c.document_id AND r.source_locator=c.source_locator
    WHERE c.corrected_product_id=$1
  ), eligible_docs AS MATERIALIZED (
    SELECT key.document_id FROM (SELECT DISTINCT document_id FROM raw_keys) key
    WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict conflict
      WHERE conflict.document_id=key.document_id OFFSET 0)
      AND EXISTS (SELECT 1 FROM published_regional_price accepted
        WHERE accepted.document_id=key.document_id OFFSET 0)
  ), scoped AS MATERIALIZED (
    SELECT k.document_id,k.source_locator,k.observed_on,k.effective_product_id AS product_id,
      k.market_name,k.presentation,k.quantity,k.source_unit,k.unit,k.round
    -- Publication eligibility in migration 078 is document-wide; resolve it
    -- once per distinct document while retaining each raw locator for options.
    FROM raw_keys k JOIN eligible_docs e ON e.document_id=k.document_id
  ), alias_overlap_keys AS MATERIALIZED (
    SELECT observed_on,lower(btrim(presentation)) AS presentation_key,quantity,
      lower(btrim(source_unit)) AS unit_key,unit,round
    FROM scoped WHERE market_name IN ${CITY_ALIAS_NAMES_SQL}
    GROUP BY observed_on,lower(btrim(presentation)),quantity,lower(btrim(source_unit)),unit,round
    HAVING count(DISTINCT market_name)>1
  ), alias_candidates AS MATERIALIZED (
    SELECT rival.document_id,rival.source_locator,rival.observed_on,rival.market_name,
      lower(btrim(rival.presentation)) AS presentation_key,rival.quantity,
      lower(btrim(rival.source_unit)) AS unit_key,rival.unit,rival.round,
      rival.min_price,rival.max_price,
      (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
      (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
      ${verifiedCityCategoryPathSql('rival_overlay','rival_class.category_path','rival')} AS category_path,
      rival_d.retrieved_at
    FROM scoped key
    JOIN alias_overlap_keys overlap ON overlap.observed_on=key.observed_on
      AND overlap.presentation_key=lower(btrim(key.presentation)) AND overlap.quantity=key.quantity
      AND overlap.unit_key=lower(btrim(key.source_unit)) AND overlap.unit=key.unit AND overlap.round=key.round
    JOIN regional_price rival ON rival.document_id=key.document_id AND rival.source_locator=key.source_locator
    JOIN source_document rival_d ON rival_d.id=rival.document_id
    LEFT JOIN regional_classification rival_class
      ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
    LEFT JOIN verified_regional_category_overlay rival_overlay
      ON rival_overlay.document_id=rival.document_id AND rival_overlay.source_locator=rival.source_locator
    WHERE key.market_name IN ${CITY_ALIAS_NAMES_SQL}
  ), alias_latest AS MATERIALIZED (
    SELECT DISTINCT ON (observed_on,presentation_key,quantity,unit_key,unit,round,market_name)
      observed_on,presentation_key,quantity,unit_key,unit,round,market_name,
      min_price,max_price,min_unit_price,max_unit_price,category_path
    FROM alias_candidates
    ORDER BY observed_on,presentation_key,quantity,unit_key,unit,round,market_name,
      retrieved_at DESC,document_id DESC,source_locator
  ), alias_conflicts AS MATERIALIZED (
    SELECT observed_on,presentation_key,quantity,unit_key,unit,round
    FROM alias_latest
    GROUP BY observed_on,presentation_key,quantity,unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
      AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
  ), city_dimensions AS MATERIALIZED (
    SELECT DISTINCT ${cityMarketIdSql()} AS market_id,${cityMarketNameSql()} AS market_name,
      lower(btrim(r.presentation)) AS presentation_key,r.quantity,
      lower(btrim(r.source_unit)) AS unit_key,
      upper(left(r.presentation,1)) || lower(substr(r.presentation,2)) AS presentation,
      ${cityFilterUnitsSql()} AS units,
      min(r.observed_on) OVER (PARTITION BY ${cityMarketIdSql()},
        upper(left(r.presentation,1)) || lower(substr(r.presentation,2)),${cityFilterUnitsSql()}) AS first_report_on,
      max(r.observed_on) OVER (PARTITION BY ${cityMarketIdSql()},
        upper(left(r.presentation,1)) || lower(substr(r.presentation,2)),${cityFilterUnitsSql()}) AS last_report_on
    FROM scoped r JOIN market m ON ${cityMarketJoinSql()}
    JOIN source_document d ON d.id=r.document_id
    WHERE r.product_id=$1 AND ($2='' OR translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
      AND r.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      AND NOT coalesce((m.municipality_id='11001' AND m.name IN ${CITY_ALIAS_NAMES_SQL}
        AND EXISTS (SELECT 1 FROM alias_conflicts conflict
          WHERE conflict.observed_on=r.observed_on
            AND conflict.presentation_key=lower(btrim(r.presentation))
            AND conflict.quantity=r.quantity
            AND conflict.unit_key=lower(btrim(r.source_unit))
            AND conflict.unit=r.unit AND conflict.round=r.round)),false)
  ), ambiguity AS (
    SELECT (EXISTS(SELECT 1 FROM city_dimensions
      GROUP BY market_id,presentation_key,quantity,unit_key HAVING count(*)>1)
      OR EXISTS(SELECT 1 FROM city_dimensions
      GROUP BY market_id,presentation_key,quantity,units
      HAVING count(DISTINCT unit_key)>1)) AS requires_revision_resolution
  ), options AS (
    SELECT DISTINCT
      CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
      m.id AS market_id,${ordinaryMarketOptionNameSql("CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' ELSE 'monthly' END", "m.name", "m.region")} AS market_name,'Por unidad de medida'::text AS presentation,
      CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
      NULL::date AS first_report_on,NULL::date AS last_report_on
    FROM published_price_observation o JOIN market m ON m.id=o.market_id
    WHERE o.product_id=$1 AND ($2='' OR translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
      AND o.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
    UNION
    SELECT 'city',market_id,market_name,presentation,units,first_report_on,last_report_on FROM city_dimensions
  ) SELECT options.*,ambiguity.requires_revision_resolution FROM options CROSS JOIN ambiguity
    ORDER BY series,market_name,presentation,units`;

// The accepted migration-078 view makes publication eligibility document-wide.
// Use the cheaper equivalent only while the live view definition is byte-for-byte
// the reviewed one; any unknown definition stays on the view-backed query above.
export const PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256 =
  "e804ec4ef27f4a19a194d6ff68933ac619524c591c5cb9b7551ab884cbe4c6a0";
const FILTER_OPTIONS_VIEW_HASH_SQL = `
  SELECT CASE WHEN c.relkind IN ('v','m')
    THEN encode(sha256(convert_to(pg_get_viewdef(c.oid,true),'UTF8')),'hex')
    ELSE NULL END AS definition_sha256
  FROM (SELECT pg_catalog.to_regclass('public.published_regional_price')::oid AS oid) resolved
  LEFT JOIN pg_catalog.pg_class c ON c.oid=resolved.oid`;
const FILTER_OPTIONS_078_ELIGIBILITY = `      AND EXISTS (SELECT 1 FROM published_regional_price accepted
        WHERE accepted.document_id=key.document_id OFFSET 0)`;
const FILTER_OPTIONS_078_DIRECT_ELIGIBILITY = `      AND (
        NOT EXISTS (
          SELECT 1 FROM source_archive_member enrolled_member
          JOIN dane_city_revision_source enrolled_source
            ON enrolled_source.archive_id=enrolled_member.archive_id
          WHERE enrolled_member.document_id=key.document_id
        )
        OR EXISTS (
          SELECT 1 FROM source_archive_member active_member
          JOIN dane_city_cohort_current active_head
            ON active_head.archive_id=active_member.archive_id
          WHERE active_member.document_id=key.document_id
        )
        OR EXISTS (
          SELECT 1 FROM ingestion_asset direct_asset
          WHERE direct_asset.document_id=key.document_id
            AND direct_asset.kind='city-pdf'
        )
        OR EXISTS (
          SELECT 1 FROM source_archive_member legacy_member
          WHERE legacy_member.document_id=key.document_id
            AND NOT EXISTS (
              SELECT 1 FROM dane_city_revision_source enrolled_legacy_parent
              WHERE enrolled_legacy_parent.archive_id=legacy_member.archive_id
            )
        )
      )`;
if (PRODUCT_FILTER_OPTIONS_SQL.split(FILTER_OPTIONS_078_ELIGIBILITY).length !== 2) {
  throw new Error("FILTER_OPTIONS_078_ELIGIBILITY_ANCHOR_MISMATCH");
}
export const PRODUCT_FILTER_OPTIONS_078_SQL = PRODUCT_FILTER_OPTIONS_SQL.replace(
  FILTER_OPTIONS_078_ELIGIBILITY,
  FILTER_OPTIONS_078_DIRECT_ELIGIBILITY,
);

// Preserve separately stored classification corrections and every historical path.
export const PRODUCT_CLASSIFICATIONS_SQL = `
  SELECT DISTINCT ${verifiedCityCategoryPathSql('o','c.category_path','raw')} AS category_path
  FROM (
    SELECT DISTINCT resolved.document_id,resolved.source_locator
    FROM resolved_regional_price resolved
    JOIN published_regional_price accepted
      ON accepted.document_id=resolved.document_id AND accepted.source_locator=resolved.source_locator
    WHERE resolved.product_id=$1
  ) r
  LEFT JOIN verified_regional_category_overlay o ON o.document_id=r.document_id AND o.source_locator=r.source_locator
  LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
  LEFT JOIN regional_price raw ON raw.document_id=r.document_id AND raw.source_locator=r.source_locator
  ORDER BY category_path`;

export type PriceFilters = {
  series?: string;
  market?: string;
  presentation?: string;
  units?: string;
  history?: string;
};
type ProductMarketQuote = {
  id: string; name: string; region: string; city: string;
  market_id: string; source_market_id: string | null; market_name: string; product_id: string;
  product_name: string; category: string;
  date: string; observed_on: string; price: number;
  min_price: number | null; max_price: number | null;
  series: string; unit: string; units: string; presentation: string;
  document_id: string; source_locator: string; source_url: string;
  source_page: number; category_path: string[]; source_units?: string | null;
};
type ProductHistoryPoint = {
  date: string; price: number; market_count: number;
  sources: {
    document_id: string; source_locator: string | null; source_page: number | null;
    market_id: string; source_market_id: string | null; market_name: string;
  }[];
};
type ProductDetail = Awaited<ReturnType<typeof readFilteredProduct>>;
const productDetailPending = new WeakMap<object, Map<string, Promise<ProductDetail>>>();
type ProductFilterOption = {
  series: string; market_id: string; market_name: string;
  presentation: string; units: string; requires_revision_resolution?: boolean;
  first_report_on?: string | null; last_report_on?: string | null;
};
type FilterOptions = { options: ProductFilterOption[]; ambiguousPackages: boolean };
const productOptionsPending = new WeakMap<object, Map<string, Promise<FilterOptions>>>();

export async function readProductFilterOptionsSnapshot(
  db: ReturnType<typeof database>,
  id: string,
  region: string,
  expectedViewHash = PRODUCT_FILTER_OPTIONS_078_VIEW_SHA256,
): Promise<FilterOptions> {
  const client = await db.connect();
  let transactionStarted = false;
  try {
    // Keep the schema guard and the selected query on one MVCC snapshot. A
    // concurrent migration therefore cannot make a recognized hash stale.
    // ACCESS SHARE also holds the view definition stable against CREATE OR
    // REPLACE VIEW until this read-only transaction commits; it does not block
    // ordinary row writes from ingestion.
    await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
    transactionStarted = true;
    await client.query("LOCK TABLE public.published_regional_price IN ACCESS SHARE MODE");
    const view = (await client.query<{ definition_sha256: string | null }>(FILTER_OPTIONS_VIEW_HASH_SQL)).rows[0];
    const actualHash = view?.definition_sha256 ?? null;
    const sql = actualHash === expectedViewHash
      ? PRODUCT_FILTER_OPTIONS_078_SQL
      : PRODUCT_FILTER_OPTIONS_SQL;
    let options = (await client.query<ProductFilterOption>(sql, [id, region])).rows;
    const ambiguousPackages = options.some((option) => option.requires_revision_resolution);
    if (ambiguousPackages) {
      // Keep the ambiguity fallback inside the same guarded RR snapshot as the
      // 078 definition check. This preserves the legacy winner/options semantics
      // without reading the entire quote union for unrelated products.
      options = (await client.query<ProductFilterOption>(
        PRODUCT_FILTER_OPTIONS_AMBIGUOUS_QUOTES_SQL, [id, region],
      )).rows;
    }
    await client.query("COMMIT");
    transactionStarted = false;
    return { options, ambiguousPackages };
  } catch (error) {
    if (transactionStarted) await client.query("ROLLBACK").catch(() => {});
    throw error;
  } finally {
    client.release();
  }
}

async function readFilterOptions(db: ReturnType<typeof database>, id: string, region: string): Promise<FilterOptions> {
  let pending = productOptionsPending.get(db);
  if (!pending) {
    pending = new Map();
    productOptionsPending.set(db, pending);
  }
  const key = JSON.stringify([id, region]);
  const active = pending.get(key);
  if (active) return active;
  // Different package selections use the same retained filter dimensions.
  // Share only overlapping reads; newly imported packages remain immediately
  // discoverable on the next completed request.
  const work = (async () => {
    return readProductFilterOptionsSnapshot(db, id, region);
  })().finally(() => pending!.delete(key));
  pending.set(key, work);
  return work;
}

export async function filteredProduct(
  id: string,
  region: string,
  requested: PriceFilters,
) {
  const db = database();
  requested = requested.market
    ? { ...requested, market: await withProductDetailStage("market_alias", () => resolveMarketAlias(db, requested.market!)) }
    : requested;
  let pending = productDetailPending.get(db);
  if (!pending) {
    pending = new Map();
    productDetailPending.set(db, pending);
  }
  const key = JSON.stringify([id, region,
    ...(["series", "market", "presentation", "units", "history"] as const)
      .map((field) => requested[field] || "")]);
  const active = pending.get(key);
  if (active) return active;
  if (pending.size >= 64) throw new Error("PRODUCT_DETAIL_BUSY");
  // Readers of the same exact filters share only work already in flight.
  // Completed prices and failures are never retained, so a newly published
  // original is visible on the next request without a cache refresh window.
  const work = readFilteredProduct(db, id, region, requested)
    .finally(() => pending!.delete(key));
  pending.set(key, work);
  return work;
}

async function readFilteredProduct(
  db: ReturnType<typeof database>,
  id: string,
  region: string,
  requested: PriceFilters,
) {
  const product = (await withProductDetailStage("product_lookup", () =>
    db.query("SELECT * FROM product WHERE id=$1", [id]))).rows[0];
  if (!product) return null;
  const { options, ambiguousPackages } = await withProductDetailStage("filter_options", () =>
    readFilterOptions(db, id, region));
  const seriesOptions = [...new Set<string>(options.map((o) => o.series))].sort(
    (a, b) => (a === "city" ? -1 : b === "city" ? 1 : a.localeCompare(b)),
  );
  const series = seriesOptions.includes(requested.series || "")
    ? requested.series!
    : seriesOptions[0] || "monthly";
  const market = series === "city" ? resolveCityMarketId(requested.market || "") : requested.market || "";
  const presentations = [
    ...new Set<string>(options.filter((o) => o.series === series).map((o) => o.presentation)),
  ];
  const preferred = defaultProductPackage(options, series, market,
    requested.presentation || "", requested.units || "");
  const presentation = preferred.presentation;
  const unitOptions = [
    ...new Set<string>(options
      .filter((o) => o.series === series && o.presentation === presentation)
      .map((o) => o.units)),
  ];
  const legacyUnits = incomingCityPackageUnits(
    id, requested.series === "city" ? requested.market || "" : "",
    requested.presentation || "", requested.units || "", options,
  );
  const units = legacyUnits || preferred.units;
  const matchingMarkets = new Map(options
    .filter((option) => option.series === series &&
      option.presentation === presentation && option.units === units)
    .map((option) => [option.market_id, { id: option.market_id, name: option.market_name,
      first_report_on: option.first_report_on ?? null,last_report_on: option.last_report_on ?? null }]));
  // Keep a saved, now-unavailable selection visible without offering other
  // series or package sizes as if they reported the requested price.
  const unavailableMarket = market && !matchingMarkets.has(market)
    ? options.find((option) => option.market_id === market) : undefined;
  if (unavailableMarket) matchingMarkets.set(market, {
    id: market,
    name: unavailableMarket.market_name + " · sin reportes para estos filtros",
    first_report_on: null,last_report_on: null,
  });
  const historical = requested.history === "all";
  const filter = `product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ')) AND series=$3 AND presentation=$4 AND units=$5 AND ($6='' OR market_id=$6) AND ${historical ? "observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date" : WINDOW}`;
  const marketIds = [...new Set(options.filter((option) =>
    option.series === series && option.presentation === presentation && option.units === units &&
    (!market || option.market_id === market)).map((option) => option.market_id))];
  const args = [id, region, series, presentation, units, market, marketIds];
  // Ordinary single-market city requests read all original package spellings
  // through the source-scoped path before choosing each dated revision.
  // Multi-market partitioning and the Corabastos alias route stay separate.
  const ordinaryScoped = series === "city" && !ambiguousPackages && marketIds.length > 1;
  const partitioned = series === "city" && !ambiguousPackages && marketIds.length > PARTITION_MARKETS;
  const singleOrdinaryScoped = series === "city" && marketIds.length === 1 &&
    marketIds[0] !== CORABASTOS_CITY_MARKET_ID;
  const selectedSql = (scoped: boolean, partial: boolean, allPackages = false) =>
      `${scoped ? selectedOrdinaryScopeCtes(!historical, allPackages) + "," : "WITH"} selected AS MATERIALIZED (
        SELECT selected_market_quotes.* FROM unnest($7::text[]) AS requested_market(id)
        JOIN market selected_market ON selected_market.id=requested_market.id
        AND selected_market.id<>'${CORABASTOS_CITY_MARKET_ID}'
        CROSS JOIN LATERAL (
          WITH quotes AS (${allPackages ? PRODUCT_DETAIL_QUOTE_SCOPED_VALUES : scoped ? PRODUCT_DETAIL_PACKAGE_SCOPED_VALUES : ambiguousPackages ? PRODUCT_DETAIL_QUOTE_VALUES : PRODUCT_DETAIL_PACKAGE_VALUES})
          SELECT * FROM quotes WHERE ${filter} AND market_id=selected_market.id OFFSET 0
        ) selected_market_quotes
        UNION ALL
        SELECT alias_quotes.* FROM market selected_market
        CROSS JOIN LATERAL (
          WITH quotes AS (${ambiguousPackages ? PRODUCT_DETAIL_ALIAS_QUOTE_VALUES : PRODUCT_DETAIL_ALIAS_PACKAGE_VALUES})
          SELECT * FROM quotes WHERE ${filter} AND market_id=selected_market.id OFFSET 0
        ) alias_quotes
        WHERE selected_market.id='${CORABASTOS_CITY_MARKET_ID}'
          AND selected_market.id=ANY($7::text[])
      ), latest AS (
        SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date
        FROM selected ORDER BY market_id,observed_on DESC
      ), history AS (
        SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count,${partial ? "sum(price)::text AS price_sum,count(*) AS price_count," : ""}
          coalesce(jsonb_agg(DISTINCT jsonb_build_object(
            'document_id',document_id,'source_locator',source_locator,'source_page',source_page,
            'market_id',market_id,'source_market_id',source_market_id,'market_name',market_name,
            'source_units',source_units
          )) FILTER (WHERE document_id IS NOT NULL),'[]'::jsonb) AS sources
        FROM selected GROUP BY observed_on
      ) SELECT
        coalesce((SELECT jsonb_agg(latest ORDER BY market_id) FROM latest),'[]'::jsonb) AS markets,
        coalesce((SELECT jsonb_agg(history ORDER BY date) FROM history),'[]'::jsonb) AS history`;
  const [quotes, additionalReferences] = await Promise.all([
    withProductDetailStage("selected_quotes", () => partitioned
      ? partitionedCityQuotes(db,selectedSql(true,true),args,marketIds,true)
      : ordinaryScoped || singleOrdinaryScoped
        ? selectedOrdinarySnapshotQuery<{ markets: ProductMarketQuote[]; history: ProductHistoryPoint[] }>(
          db,selectedSql(ordinaryScoped || singleOrdinaryScoped,false,singleOrdinaryScoped),args,
        )
        : db.query<{ markets: ProductMarketQuote[]; history: ProductHistoryPoint[] }>(selectedSql(false,false),args)),
    region ? Promise.resolve([]) : withProductDetailStage("summary_references", () =>
      summaryReferencesForProduct(product.name)),
  ]);
  const history = quotes.rows[0].history;
  const classifiedMarkets = await withProductDetailStage("classification", () =>
    withQuoteClassifications(quotes.rows[0].markets));
  const latest = history.at(-1);
  const classification = currentClassifications(classifiedMarkets, product.category, latest?.date)
    .map((path) => path.map((part) => normalizeLabel(part, "category")));
  return {
    product: { ...product,
      name: normalizeLabel(product.name, "product"),
      category: normalizeLabel(product.category, "category"),
    },
    markets: classifiedMarkets.map((quote) => ({ ...quote,
      product_name: normalizeLabel(quote.product_name, "product"),
      category: normalizeLabel(quote.category, "category"),
      category_path: quote.category_path.map((part) => normalizeLabel(part, "category")),
      market_name: normalizeLabel(quote.market_name, "place"),
      name: normalizeLabel(quote.name, "place"),
    })),
    history: history.map((point) => ({ ...point,
      sources: point.sources?.map((source) => ({ ...source,
        market_name: normalizeLabel(source.market_name, "place"),
      })),
    })),
    current: latest || null,
    classification,
    additional_references: additionalReferences.map(normalizeOfficialLabels),
    option_dimensions: { product_id: id, region, options },
    filters: {
      region,
      series,
      presentation,
      units,
      market,
      history: historical ? "all" : "recent",
    },
    options: {
      series: seriesOptions,
      presentations,
      units: unitOptions,
      markets: Array.from(matchingMarkets.values()).map((option) => ({ ...option,
        literal_name: option.name,
        name: normalizeLabel(option.name, "place"),
      })),
    },
  };
}
