import "server-only";
import { createHash } from "node:crypto";
import { database } from "./db";
import { CORABASTOS_CITY_MARKET_ID, cityMarketIdSql, cityMarketNamesForIdSql } from "./city-market-alias";
import { cityPriceQuotes } from "./price-quotes";
import { verifiedCityCategoryPathSql } from "./category-path-sql";
import type { ComparisonQuote } from "../comparison-types";

// Exact four-literal Corabastos city/all route. Keep the source-derived raw ID
// seed conservative: it includes held documents so no eligible product is lost.
export const CORABASTOS_RAW_PRODUCT_SEED_SQL = `WITH RECURSIVE product_ids(product_id) AS (
  (SELECT r.product_id FROM regional_price r ORDER BY r.product_id LIMIT 1)
  UNION ALL
  SELECT next.product_id FROM product_ids previous CROSS JOIN LATERAL (
    SELECT r.product_id FROM regional_price r
    WHERE r.product_id>previous.product_id ORDER BY r.product_id LIMIT 1
  ) next
)
SELECT p.product_id FROM product_ids p WHERE EXISTS (
  SELECT 1 FROM regional_price r WHERE r.product_id=p.product_id
    AND r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    AND r.observed_on<=CURRENT_DATE OFFSET 0
) ORDER BY p.product_id
`;
export const CORABASTOS_ALIAS_OVERLAP_DATES_SQL = `SELECT observed_on FROM (
 SELECT DISTINCT r.observed_on,r.market_name FROM regional_price r
 WHERE r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
   AND r.observed_on<=CURRENT_DATE
) raw_date_names GROUP BY observed_on HAVING min(market_name)<>max(market_name) ORDER BY observed_on`;
// Typed winner seek, then full-document publication, verified category and
// metadata-collision checks. Any correction/collision is sent to exact fallback.
export const CORABASTOS_TYPED_BATCH_SQL = `WITH alias_overlap_dates AS MATERIALIZED (
  SELECT unnest($2::date[]) AS observed_on
), alias_exception AS MATERIALIZED (
  SELECT coalesce(c.corrected_product_id,r.product_id) AS effective_product_id
  FROM regional_price r JOIN alias_overlap_dates d ON d.observed_on=r.observed_on
  LEFT JOIN regional_price_product_correction c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
  WHERE r.product_id=ANY($1::text[]) AND r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
  GROUP BY coalesce(c.corrected_product_id,r.product_id),r.observed_on,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit))
  HAVING min(r.market_name)<>max(r.market_name)
), key_profile AS MATERIALIZED (
  SELECT coalesce(c.corrected_product_id,r.product_id) AS effective_product_id,r.market_name,
    lower(btrim(r.presentation)) AS presentation_key,r.quantity,lower(btrim(r.source_unit)) AS source_unit_key,r.unit,
    bool_or(c.document_id IS NOT NULL) AS corrected_any,
    min(upper(left(r.presentation,1))||lower(substr(r.presentation,2))) AS min_presentation,
    max(upper(left(r.presentation,1))||lower(substr(r.presentation,2))) AS max_presentation,
    min(r.quantity::float8::text||' '||upper(left(r.source_unit,1))||lower(substr(r.source_unit,2))) AS min_units,
    max(r.quantity::float8::text||' '||upper(left(r.source_unit,1))||lower(substr(r.source_unit,2))) AS max_units
  FROM regional_price r LEFT JOIN regional_price_product_correction c
    ON c.document_id=r.document_id AND c.source_locator=r.source_locator
  WHERE r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    AND r.observed_on<=CURRENT_DATE AND r.product_id=ANY($1::text[])
  GROUP BY coalesce(c.corrected_product_id,r.product_id),r.market_name,lower(btrim(r.presentation)),
    r.quantity,lower(btrim(r.source_unit)),r.unit
), unit_exception AS MATERIALIZED (
  SELECT effective_product_id FROM key_profile
  GROUP BY effective_product_id,market_name,presentation_key,quantity,source_unit_key
  HAVING min(unit)<>max(unit)
), display_exception AS MATERIALIZED (
  SELECT effective_product_id FROM key_profile
  WHERE min_presentation<>max_presentation OR min_units<>max_units
), display_variant_keys AS MATERIALIZED (
  SELECT DISTINCT effective_product_id,presentation_key,quantity,source_unit_key,
    min_presentation AS display_presentation,min_units AS display_units,unit
  FROM key_profile
), display_collision AS MATERIALIZED (
  SELECT effective_product_id FROM display_variant_keys
  GROUP BY effective_product_id,display_presentation,display_units,unit
  HAVING count(*)>1
), exception_products AS MATERIALIZED (
  SELECT effective_product_id AS product_id FROM key_profile WHERE corrected_any
  UNION SELECT effective_product_id FROM alias_exception
  UNION SELECT effective_product_id FROM unit_exception
  UNION SELECT effective_product_id FROM display_exception
  UNION SELECT effective_product_id FROM display_collision
), ordinary_keys AS MATERIALIZED (
  SELECT k.effective_product_id AS product_id,k.market_name,k.presentation_key,k.quantity,k.source_unit_key,k.unit
  FROM key_profile k WHERE NOT EXISTS (SELECT 1 FROM exception_products x WHERE x.product_id=k.effective_product_id)
), key_latest AS MATERIALIZED (
  SELECT k.product_id,k.market_name,k.presentation_key,k.quantity,k.source_unit_key,k.unit,
    newest.document_id,newest.source_locator,newest.observed_on,newest.presentation,newest.source_unit,
    newest.round,newest.retrieved_at
  FROM ordinary_keys k CROSS JOIN LATERAL (
    SELECT top.*,d.retrieved_at FROM (
      SELECT r.document_id,r.source_locator,r.observed_on,r.presentation,r.source_unit,r.round
      FROM published_regional_price r
      WHERE r.product_id=k.product_id AND r.market_name=k.market_name
        AND lower(btrim(r.presentation))=k.presentation_key AND r.quantity=k.quantity
        AND lower(btrim(r.source_unit))=k.source_unit_key AND r.unit=k.unit
        AND r.observed_on<=CURRENT_DATE
        AND NOT EXISTS (SELECT 1 FROM regional_price_product_correction correction
          WHERE correction.document_id=r.document_id AND correction.source_locator=r.source_locator)
      ORDER BY r.observed_on DESC,r.round DESC FETCH FIRST 1 ROWS WITH TIES
    ) top JOIN source_document d ON d.id=top.document_id
    ORDER BY d.retrieved_at DESC,top.source_locator LIMIT 1
  ) newest
), display_keys AS MATERIALIZED (
  SELECT k.product_id,'sipsa-bogota-d-c-corabastos'::text AS market_id,k.observed_on,k.document_id,k.source_locator,
    upper(left(k.presentation,1))||lower(substr(k.presentation,2)) AS presentation,
    k.quantity::float8::text||' '||upper(left(k.source_unit,1))||lower(substr(k.source_unit,2)) AS units,k.unit
  FROM key_latest k JOIN market m ON m.name=(CASE WHEN k.market_name='Bogotà, Corabastos'
      THEN 'Bogotá, D.C., Corabastos' ELSE k.market_name END)
  WHERE m.municipality_id='11001' AND m.name IN
    ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
), final_winner_ids AS MATERIALIZED (
  SELECT DISTINCT ON (product_id,market_id,presentation,units,unit)
    product_id,market_id,observed_on,document_id,source_locator,presentation,units,unit
  FROM display_keys
  ORDER BY product_id,market_id,presentation,units,unit,observed_on DESC,document_id
), ordinary_rows AS MATERIALIZED (
SELECT f.product_id AS id,
  CASE WHEN correction.document_id IS NULL THEN r.product_name ELSE correction.corrected_product_name END AS name,
  coalesce(overlay.corrected_category,r.category) AS category,
  ${verifiedCityCategoryPathSql('overlay','classification.category_path','r')} AS category_path,
  f.presentation,f.units,f.unit,'city'::text AS series,f.market_id AS location_id,
  CASE WHEN r.market_name='Bogotà, Corabastos' THEN NULL::text ELSE m.id END AS source_market_id,
  r.market_name AS location_name,m.region AS department,
  (coalesce(money.corrected_min_price,r.min_price)+coalesce(money.corrected_max_price,r.max_price))/2 AS price,
  coalesce(money.corrected_min_price,r.min_price) AS min_price,
  coalesce(money.corrected_max_price,r.max_price) AS max_price,
  f.observed_on AS date,r.document_id,r.source_locator,r.source_page,
  r.quantity::float8::text || ' ' || r.source_unit AS source_units
FROM final_winner_ids f JOIN regional_price r ON r.document_id=f.document_id AND r.source_locator=f.source_locator
JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos' THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END) AND m.municipality_id='11001'
JOIN source_document d ON d.id=r.document_id
LEFT JOIN regional_price_product_correction correction ON correction.document_id=r.document_id AND correction.source_locator=r.source_locator
LEFT JOIN verified_regional_category_overlay overlay ON overlay.document_id=r.document_id AND overlay.source_locator=r.source_locator
LEFT JOIN regional_classification classification ON classification.document_id=r.document_id AND classification.source_locator=r.source_locator
LEFT JOIN verified_city_pdf_price_overlay money ON money.document_id=r.document_id AND money.source_locator=r.source_locator
), overlay_collision AS MATERIALIZED (
  SELECT id AS product_id FROM ordinary_rows
  GROUP BY id,document_id,source_locator HAVING count(*)>1
 )
SELECT 0::int AS row_kind,o.*,NULL::text AS exception_product_id FROM ordinary_rows o
UNION ALL
SELECT 1::int AS row_kind,o.*,e.product_id AS exception_product_id FROM exception_products e
LEFT JOIN LATERAL (SELECT * FROM ordinary_rows WHERE false) o ON true
UNION ALL
SELECT 2::int AS row_kind,o.*,e.product_id AS exception_product_id FROM (SELECT DISTINCT product_id FROM overlay_collision) e
LEFT JOIN LATERAL (SELECT * FROM ordinary_rows WHERE false) o ON true
ORDER BY row_kind,id,presentation,units,unit,series,date DESC,document_id
`;
// Same cityPriceQuotes source/ranking/conflict semantics. The only new
// restriction is an indexed raw-product superset of requested effective IDs.
export const CORABASTOS_INDEXED_EXCEPTION_SQL = `WITH exception_raw_ids AS MATERIALIZED (
  SELECT id AS product_id FROM unnest($2::text[]) AS requested(id)
  UNION
  SELECT raw.product_id FROM regional_price_product_correction correction
  JOIN regional_price raw ON raw.document_id=correction.document_id
    AND raw.source_locator=correction.source_locator
  WHERE correction.corrected_product_id=ANY($2::text[])
), exception_source_rows AS MATERIALIZED (
  SELECT sought.* FROM exception_raw_ids source_product
  CROSS JOIN LATERAL (
    SELECT sought.* FROM published_regional_price sought
    WHERE sought.product_id=source_product.product_id
      AND sought.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
      AND sought.observed_on<=CURRENT_DATE OFFSET 0
  ) sought
), city_alias_witnesses AS MATERIALIZED (
      SELECT rival.document_id,rival.source_locator,rival_d.retrieved_at,
        coalesce(rival_c.corrected_product_id,rival.product_id) AS product_id,
        rival.observed_on,lower(btrim(rival.presentation)) AS presentation_key,
        rival.quantity,lower(btrim(rival.source_unit)) AS source_unit_key,
        rival.unit,rival.round,rival.market_name,rival.min_price,rival.max_price,
        (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
        (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
        ${verifiedCityCategoryPathSql('rival_overlay','rival_class.category_path','rival')} AS category_path
      FROM exception_source_rows rival
      JOIN source_document rival_d ON rival_d.id=rival.document_id
      LEFT JOIN regional_classification rival_class
        ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
      LEFT JOIN verified_regional_category_overlay rival_overlay
        ON rival_overlay.document_id=rival.document_id AND rival_overlay.source_locator=rival.source_locator
      LEFT JOIN regional_price_product_correction rival_c
        ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
      WHERE rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') AND rival.observed_on<=CURRENT_DATE AND coalesce(rival_c.corrected_product_id,rival.product_id)=ANY($2::text[])
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
  ), exception_quote_rows AS MATERIALIZED (
    SELECT raw.document_id,raw.source_locator,raw.observed_on,
      CASE WHEN correction.document_id IS NULL THEN raw.product_id ELSE correction.corrected_product_id END AS product_id,
      CASE WHEN correction.document_id IS NULL THEN raw.product_name ELSE correction.corrected_product_name END AS product_name,
      raw.market_name,coalesce(overlay.corrected_category,raw.category) AS category,
      raw.presentation,raw.quantity,raw.source_unit,raw.round,raw.round_label,
      raw.min_price,raw.max_price,raw.unit,raw.min_unit_price,raw.max_unit_price,raw.source_page
    FROM exception_source_rows raw
    LEFT JOIN regional_price_product_correction correction
      ON correction.document_id=raw.document_id AND correction.source_locator=raw.source_locator
    LEFT JOIN verified_regional_category_overlay overlay
      ON overlay.document_id=raw.document_id AND overlay.source_locator=raw.source_locator
    WHERE (CASE WHEN correction.document_id IS NULL THEN raw.product_id ELSE correction.corrected_product_id END)=ANY($2::text[])
  ), quotes AS (
  SELECT product_id,market_id,source_market_id,market_name,city,region,product_name,category,category_path,
    observed_on,(min_price+max_price)/2 AS price,min_price,max_price,comparison_unit AS unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,document_id,source_locator,source_url,'daily'::text AS period,source_page,source_units FROM (
    
    SELECT DISTINCT ON(r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE lower(btrim(r.source_unit)) END)
      r.*,CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g' ELSE r.unit END AS comparison_unit,r.quantity::float8::text || ' ' || r.source_unit AS source_units,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END) AS market_id,(CASE WHEN r.market_name='Bogotà, Corabastos' THEN NULL::text ELSE m.id END) AS source_market_id,m.city,m.region,
      string_to_array(r.category,' > ') AS category_path,
      CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END AS units,d.source_url
    FROM exception_quote_rows r JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos'
    THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END)
    JOIN source_document d ON d.id=r.document_id
    
    WHERE r.market_name=ANY(CASE WHEN $1='sipsa-bogota-d-c-corabastos'
    THEN ARRAY['Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos']::text[]
    ELSE ARRAY[(SELECT name FROM market WHERE id=$1)]::text[] END)
    AND (CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END)=$1 AND r.product_id=ANY($2::text[])
    AND r.observed_on<=CURRENT_DATE
    AND NOT EXISTS (SELECT 1 FROM excluded_city_alias_rows conflict
             WHERE conflict.document_id=r.document_id AND conflict.source_locator=r.source_locator)
    ORDER BY r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE lower(btrim(r.source_unit)) END,r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city)
  SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
    product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
    market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
    price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
  FROM quotes WHERE true AND observed_on<=CURRENT_DATE
  ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`;
const exactScope = `WHERE ${cityMarketNamesForIdSql("$1")}
  AND ${cityMarketIdSql()}=$1 AND r.product_id=$2 AND r.observed_on<=CURRENT_DATE`;
// Keep the source-view shortcut bound to its exact qualified published definition.
// The held IDs come from the live unresolved view in the same RR snapshot.
export const CORABASTOS_PUBLISHED_VIEW_SHA256 =
  "b6b773cdb0e1450f926c53d97bcdf4665cb39b3108bf5abb63a6d71b141b0e40";
export const CORABASTOS_PUBLISHED_VIEW_SQL =
  "SELECT pg_get_viewdef('published_regional_price'::regclass,true) AS definition";
export const CORABASTOS_HELD_DOCUMENTS_SQL =
  "SELECT DISTINCT document_id FROM unresolved_city_pdf_publication_conflict ORDER BY document_id";
function replaceExactlyOnce(sql: string, source: string, replacement: string): string {
  const at = sql.indexOf(source);
  if (at < 0 || sql.indexOf(source, at + source.length) >= 0)
    throw new Error("CORABASTOS_SOURCE_BINDING_SHAPE_CHANGED");
  return sql.slice(0, at) + replacement + sql.slice(at + source.length);
}
export const CORABASTOS_BOUND_TYPED_SQL = replaceExactlyOnce(
  CORABASTOS_TYPED_BATCH_SQL,
  "FROM published_regional_price r\n      WHERE",
  "FROM regional_price r\n      WHERE r.document_id <> ALL($3::text[]) AND",
);
export const CORABASTOS_BOUND_EXCEPTION_SQL = replaceExactlyOnce(
  CORABASTOS_INDEXED_EXCEPTION_SQL,
  "FROM published_regional_price sought\n    WHERE",
  "FROM regional_price sought\n    WHERE sought.document_id <> ALL($3::text[]) AND",
);
// A conflicting city alias requires two distinct source market literals on the
// same date. The raw-source date set is a conservative superset, including
// held rows; narrow only the conflict witness, never quote/source selection.
export const CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL = replaceExactlyOnce(
  CORABASTOS_BOUND_EXCEPTION_SQL,
  "WHERE rival.market_name IN ('Bogotá, Corabastos'",
  "WHERE rival.observed_on=ANY($4::date[]) AND rival.market_name IN ('Bogotá, Corabastos'",
);

export const CORABASTOS_EXACT_PRODUCT_SQL = `WITH quotes AS (${cityPriceQuotes(false, exactScope)})
  SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
    product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
    market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
    price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
  FROM quotes WHERE true AND observed_on<=CURRENT_DATE
  ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`;
export const CORABASTOS_ORIGINAL_ORDER_SQL = `SELECT ord
  FROM unnest($1::text[],$2::text[],$3::text[],$4::text[],$5::text[],$6::date[],$7::text[])
  WITH ORDINALITY AS t(id,presentation,units,unit,series,day,document_id,ord)
  ORDER BY id,presentation,units,unit,series,day DESC,document_id`;
export const CORABASTOS_SELECTED_CLASSIFICATIONS_SQL = `
  SELECT selected.document_id,selected.source_locator,
    ${verifiedCityCategoryPathSql('o','c.category_path','raw')} AS category_path
  FROM (SELECT DISTINCT document_id,source_locator FROM unnest($1::text[],$2::text[]) AS input(document_id,source_locator)) selected
  LEFT JOIN verified_regional_category_overlay o ON o.document_id=selected.document_id AND o.source_locator=selected.source_locator
  LEFT JOIN regional_classification c ON c.document_id=selected.document_id AND c.source_locator=selected.source_locator
  LEFT JOIN regional_price raw ON raw.document_id=selected.document_id AND raw.source_locator=selected.source_locator`;

type TypedBatchRow = ComparisonQuote & { row_kind: number; exception_product_id: string | null };
type FailureStage = "begin" | "binding" | "holds" | "seed" | "overlap" | "batch" | "exception" | "collision"
  | "order" | "classification" | "commit";
const BATCH_SIZE = 250;

/** One read-only source snapshot through winner selection, exact fallback and classification. */
export async function corabastosAllHistoryQuotes(): Promise<ComparisonQuote[]> {
  const client = await database().connect();
  let transactionStarted = false;
  let stage: FailureStage = "begin";
  try {
    await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY");
    transactionStarted = true;
    stage = "binding";
    const viewRows = (await client.query<{ definition: string }>(
      CORABASTOS_PUBLISHED_VIEW_SQL)).rows;
    if (viewRows.length !== 1 || typeof viewRows[0].definition !== "string")
      throw new Error("CORABASTOS_PUBLISHED_VIEW_BINDING_UNAVAILABLE");
    const boundView = createHash("sha256").update(viewRows[0].definition).digest("hex")
      === CORABASTOS_PUBLISHED_VIEW_SHA256;
    let heldDocuments: string[] = [];
    if (boundView) {
      stage = "holds";
      heldDocuments = (await client.query<{ document_id: string }>(
        CORABASTOS_HELD_DOCUMENTS_SQL)).rows.map((row) => row.document_id);
      if (heldDocuments.some((id) => typeof id !== "string" || !id)
        || heldDocuments.length !== new Set(heldDocuments).size)
        throw new Error("CORABASTOS_INVALID_HELD_DOCUMENT_SET");
    }
    stage = "seed";
    const rawIds = (await client.query<{ product_id: string }>(CORABASTOS_RAW_PRODUCT_SEED_SQL))
      .rows.map((row) => row.product_id);
    if (rawIds.length !== new Set(rawIds).size) throw new Error("CORABASTOS_DUPLICATE_RAW_ID");
    stage = "overlap";
    const overlapDates = (await client.query<{ observed_on: string }>(CORABASTOS_ALIAS_OVERLAP_DATES_SQL))
      .rows.map((row) => row.observed_on);
    const ordinary: ComparisonQuote[] = [];
    const exceptionIds = new Set<string>();
    const collisionIds = new Set<string>();
    stage = "batch";
    for (let offset = 0; offset < rawIds.length; offset += BATCH_SIZE) {
      const rows = (await client.query<TypedBatchRow>(
        boundView ? CORABASTOS_BOUND_TYPED_SQL : CORABASTOS_TYPED_BATCH_SQL,
        boundView
          ? [rawIds.slice(offset, offset + BATCH_SIZE), overlapDates, heldDocuments]
          : [rawIds.slice(offset, offset + BATCH_SIZE), overlapDates])).rows;
      for (const row of rows) {
        if (row.row_kind === 1 || row.row_kind === 2) {
          if (!row.exception_product_id) throw new Error("CORABASTOS_MISSING_EXCEPTION_ID");
          exceptionIds.add(row.exception_product_id);
          if (row.row_kind === 2) collisionIds.add(row.exception_product_id);
        } else if (row.row_kind === 0) {
          if (row.exception_product_id !== null) throw new Error("CORABASTOS_UNEXPECTED_EXCEPTION_ID");
          const { row_kind: _kind, exception_product_id: _id, ...quote } = row;
          ordinary.push(quote);
        } else throw new Error("CORABASTOS_UNKNOWN_ROW_KIND");
      }
    }
    // Corrections can move a target product across raw-ID batches. Filter only
    // after every batch has established the global exceptional ID set.
    const chosen: ComparisonQuote[] = ordinary.filter((row) => !exceptionIds.has(row.id));
    const guardedIds = [...exceptionIds].filter((id) => !collisionIds.has(id));
    stage = "exception";
    if (guardedIds.length) chosen.push(...(await client.query<ComparisonQuote>(
      boundView ? CORABASTOS_OVERLAP_BOUND_EXCEPTION_SQL : CORABASTOS_INDEXED_EXCEPTION_SQL,
      boundView
        ? [CORABASTOS_CITY_MARKET_ID, guardedIds, heldDocuments, overlapDates]
        : [CORABASTOS_CITY_MARKET_ID, guardedIds])).rows);
    stage = "collision";
    for (const id of collisionIds) chosen.push(...(await client.query<ComparisonQuote>(
      CORABASTOS_EXACT_PRODUCT_SQL, [CORABASTOS_CITY_MARKET_ID, id])).rows);
    if (chosen.some((row) => !row?.id || !row?.document_id || !row?.source_locator))
      throw new Error("CORABASTOS_INVALID_SOURCE_IDENTITY");
    // PostgreSQL's ordering is the original DISTINCT ON order, including its
    // collation, date and source tie breaker. JS localeSort would change it.
    stage = "order";
    const ordinals = (await client.query<{ ord: string | number }>(CORABASTOS_ORIGINAL_ORDER_SQL, [
      chosen.map((row) => row.id), chosen.map((row) => row.presentation),
      chosen.map((row) => row.units), chosen.map((row) => row.unit),
      chosen.map((row) => row.series), chosen.map((row) => row.date),
      chosen.map((row) => row.document_id),
    ])).rows;
    if (ordinals.length !== chosen.length) throw new Error("CORABASTOS_ORDER_LENGTH");
    const seen = new Set<number>();
    const ordered = ordinals.map((item) => {
      const index = Number(item.ord) - 1;
      if (!Number.isSafeInteger(index) || index < 0 || index >= chosen.length || seen.has(index))
        throw new Error("CORABASTOS_ORDER_ORDINAL");
      seen.add(index);
      return chosen[index];
    });
    stage = "classification";
    const paths = (await client.query<{ document_id: string; source_locator: string; category_path: string[] }>(
      CORABASTOS_SELECTED_CLASSIFICATIONS_SQL,
      [ordered.map((row) => row.document_id), ordered.map((row) => row.source_locator)],
    )).rows;
    const bySource = new Map(paths.map((row) =>
      [JSON.stringify([row.document_id, row.source_locator]), row.category_path]));
    const result = ordered.map((row) => ({ ...row, category_path:
      bySource.get(JSON.stringify([row.document_id, row.source_locator])) || row.category_path }));
    stage = "commit";
    await client.query("COMMIT");
    transactionStarted = false;
    return result;
  } catch (error) {
    const candidate = (error as { code?: unknown })?.code;
    const sqlstate = typeof candidate === "string" && /^[0-9A-Z]{5}$/.test(candidate)
      ? candidate : undefined;
    console.error("Corabastos all-history quote query failed", { stage, sqlstate });
    if (transactionStarted) await client.query("ROLLBACK").catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}
