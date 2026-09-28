-- Milk charts repeat the previous observation month. Prefer the later validated
-- bulletin, then the most recently retained revision of that same bulletin.
-- Only the observed month-end or immediately following month-end is eligible.
-- Compare exact ISO strings; malformed metadata must never raise a date cast.
-- Original v1 rows predate bulletin_period metadata; their retained reference
-- period was independently checked against the printed report month on ingest.
-- A later parser can withdraw an ambiguous quote without changing its evidence.
-- A subsequent corrected parse can publish again, preserving all revisions.
CREATE OR REPLACE VIEW published_official_price AS
 SELECT DISTINCT ON(q.quote_key,q.observed_on) q.*
 FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
 WHERE NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
   AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
 AND NOT EXISTS(SELECT 1 FROM official_source_review r
   WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator
     AND r.created_at>=q.parsed_at)
 ORDER BY q.quote_key,q.observed_on,CASE WHEN q.series='dane-milk-macroregion'
      AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
      AND COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period) IN (
        to_char(q.observed_on,'YYYY-MM-DD'),
        to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
    THEN COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period)
    END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator;
GRANT SELECT ON published_official_price TO agro_reader,agro_ingestor;

-- Only derived milk cache entries need a bounded refresh; raw rows are immutable.
UPDATE official_catalog_current SET dirty=true
WHERE payload->>'series'='dane-milk-macroregion' AND NOT dirty;
