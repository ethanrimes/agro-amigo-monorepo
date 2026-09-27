-- Preserve historical parser output while explicitly withdrawing unverified
-- observations from publication. Corrected parses use versioned locators.
CREATE TABLE IF NOT EXISTS historical_price_review (
 document_id text NOT NULL REFERENCES source_document(id),
 source_locator text NOT NULL,
 validator_version text NOT NULL,
 reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,validator_version)
);
DROP TRIGGER IF EXISTS retain_history ON historical_price_review;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON historical_price_review
FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON historical_price_review;
CREATE TRIGGER immutable_history BEFORE UPDATE ON historical_price_review
FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON historical_price_review TO agro_ingestor;
GRANT SELECT ON historical_price_review TO agro_reader;
CREATE OR REPLACE VIEW published_historical_price AS
SELECT h.* FROM historical_price h
WHERE (h.series<>'dane-monthly-bulletin' OR h.details->>'parser_version'='monthly-pdf-v3')
AND NOT EXISTS(
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=h.document_id
 AND a.kind='monthly-annex' AND a.processor_version='monthly-annex-v2'
 AND coalesce(h.details->>'parser_version','')<>'monthly-annex-v2'
)
AND NOT EXISTS(
 SELECT 1 FROM historical_price_review r
 WHERE r.document_id=h.document_id AND r.source_locator=h.source_locator
);
GRANT SELECT ON published_historical_price TO agro_ingestor,agro_reader;

-- The view withholds the previous monthly-bulletin series as a whole pending
-- strict re-extraction. No full historical scan or deletion is necessary.
UPDATE ingestion_asset SET status='review',
 error='Legacy monthly PDF price grids require table-local monetary verification; originals and prior parser rows retained'
WHERE kind='monthly-pdf' AND status='complete' AND records>0
 AND processor_version<>'monthly-pdf-v3';
