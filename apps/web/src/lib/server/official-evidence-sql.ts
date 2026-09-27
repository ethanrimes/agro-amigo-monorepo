/** Limit source summaries on narrow immutable revision keys before fetching payloads. */
export const OFFICIAL_EVIDENCE_ROWS_SQL = `
 WITH winners AS MATERIALIZED (
   SELECT document_id,source_locator,parser_version,observed_on FROM (
     SELECT DISTINCT ON(q.source_locator)
       q.document_id,q.source_locator,q.parser_version,q.observed_on,q.parsed_at
     FROM official_price_quote q
     WHERE q.document_id=$1 AND ($2='' OR q.source_locator=$2)
       AND NOT EXISTS(SELECT 1 FROM ingestion_asset a
         WHERE a.document_id=q.document_id AND a.status='review'
           AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
       AND NOT EXISTS(SELECT 1 FROM official_source_review r
         WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator
           AND r.created_at>=q.parsed_at)
     ORDER BY q.source_locator,q.parsed_at DESC
   ) verified
   ORDER BY observed_on DESC,source_locator LIMIT 100
 )
 SELECT q.product_name,q.market,q.observed_on,q.period_start,q.price,
   q.min_price,q.max_price,q.currency,q.unit,q.basis,q.source_locator
 FROM winners w JOIN official_price_quote q
   USING(document_id,source_locator,parser_version)
 ORDER BY w.observed_on DESC,w.source_locator`;
