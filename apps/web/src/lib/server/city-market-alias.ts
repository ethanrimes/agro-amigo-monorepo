/** Four source-verified literal names for one Corabastos facility in Bogotá (11001).
 * This projection is city-series-only: original names, IDs and source rows stay intact.
 * The 2022 grave-accent literal has no market row; its source market ID remains null.
 */
import { verifiedCityCategoryPathSql } from "./category-path-sql";

export const CORABASTOS_CITY_MARKET_ID = "sipsa-bogota-d-c-corabastos";
export const CORABASTOS_CITY_MARKET_NAME = "Bogotá, D.C., Corabastos";
export const CORABASTOS_CITY_MARKET_IDS = [
  "dane-city-bogota-corabastos",
  "dane-city-bogota-d-c-corabastos",
  CORABASTOS_CITY_MARKET_ID,
] as const;
export const CORABASTOS_CITY_NAMES = [
  "Bogotá, Corabastos",
  "Bogotá D.C., Corabastos",
  CORABASTOS_CITY_MARKET_NAME,
  "Bogotà, Corabastos",
] as const;

export const CITY_ALIAS_NAMES_SQL = "('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')";
const SQL_NAMES = CITY_ALIAS_NAMES_SQL;
const SQL_CANONICAL_ID = "'sipsa-bogota-d-c-corabastos'";
const SQL_CANONICAL_NAME = "'Bogotá, D.C., Corabastos'";
const SQL_UNCURATED_NAME = "'Bogotà, Corabastos'";

/** Only the literal printed in the verified 2022 child PDF may borrow the
 * canonical market's location metadata. This never changes the raw row. */
export function cityMarketJoinSql(row = "r", market = "m"): string {
  return `${market}.name=(CASE WHEN ${row}.market_name=${SQL_UNCURATED_NAME}
    THEN ${SQL_CANONICAL_NAME} ELSE ${row}.market_name END)`;
}

/** Same match as cityMarketJoinSql, expressed as indexed literal-name seeks.
 * A raw grave-accent market row must never receive the grave-accent source row.
 */
export function cityMarketSeekSql(row = "r", market = "m"): string {
  return `((${row}.market_name=${market}.name AND ${row}.market_name<>${SQL_UNCURATED_NAME})
    OR (${market}.name=${SQL_CANONICAL_NAME} AND ${row}.market_name=${SQL_UNCURATED_NAME}))`;
}

export function citySourceMarketIdSql(row = "r", market = "m"): string {
  return `(CASE WHEN ${row}.market_name=${SQL_UNCURATED_NAME} THEN NULL::text ELSE ${market}.id END)`;
}

export function resolveCityMarketId(id: string): string {
  return (CORABASTOS_CITY_MARKET_IDS as readonly string[]).includes(id)
    ? CORABASTOS_CITY_MARKET_ID : id;
}

export function cityMarketIdSql(market = "m"): string {
  return `(CASE WHEN ${market}.municipality_id='11001' AND ${market}.name IN ${SQL_NAMES} THEN ${SQL_CANONICAL_ID} ELSE ${market}.id END)`;
}

export function cityMarketNameSql(market = "m"): string {
  return `(CASE WHEN ${market}.municipality_id='11001' AND ${market}.name IN ${SQL_NAMES} THEN ${SQL_CANONICAL_NAME} ELSE ${market}.name END)`;
}

export function cityMarketNamesForIdSql(selectedId: string, row = "r"): string {
  return `${row}.market_name=ANY(CASE WHEN ${selectedId}=${SQL_CANONICAL_ID}
    THEN ARRAY['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos']::text[]
    ELSE ARRAY[(SELECT name FROM market WHERE id=${selectedId})]::text[] END)`;
}

/** Reject only incompatible cross-literal city rows for one typed quote key.
 * Same-literal revisions remain eligible for the normal latest-source ranking.
 * The rival seek is constrained to four exact names, product and report date.
 */
export function cityCrossAliasConflictSql(
  row = "r", market = "m", effectiveProductId = `${row}.product_id`,
): string {
  return `coalesce((${market}.municipality_id='11001' AND ${market}.name IN ${SQL_NAMES}
    AND (SELECT count(DISTINCT latest.market_name)>1
                  AND count(DISTINCT (latest.min_price,latest.max_price,
                    latest.min_unit_price,latest.max_unit_price,latest.category_path))>1
      FROM (SELECT DISTINCT ON (rival.market_name)
          rival.market_name,rival.min_price,rival.max_price,
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
        WHERE rival.market_name IN ${SQL_NAMES}
          AND rival.observed_on=${row}.observed_on
          AND coalesce(rival_c.corrected_product_id,rival.product_id)=${effectiveProductId}
          AND lower(btrim(rival.presentation))=lower(btrim(${row}.presentation))
          AND rival.quantity=${row}.quantity
          AND lower(btrim(rival.source_unit))=lower(btrim(${row}.source_unit))
          AND rival.unit=${row}.unit AND rival.round=${row}.round
        ORDER BY rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
      ) latest)),false)`;
}
