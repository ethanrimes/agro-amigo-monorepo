-- Retain incorrect published identities as evidence while corrected identities
-- are published independently. A review applies to one exact original quote.
CREATE TABLE IF NOT EXISTS price_observation_review (
 document_id text NOT NULL REFERENCES source_document(id), source_locator text NOT NULL,
 product_id text NOT NULL, market_id text NOT NULL, source_id text NOT NULL,
 observed_on date NOT NULL, period text NOT NULL, unit text NOT NULL,
 reason text NOT NULL, evidence jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit)
);
DROP TRIGGER IF EXISTS retain_history ON price_observation_review;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON price_observation_review
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON price_observation_review;
CREATE TRIGGER immutable_history BEFORE UPDATE ON price_observation_review
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON price_observation_review TO agro_reader;
GRANT SELECT,INSERT ON price_observation_review TO agro_ingestor;
CREATE OR REPLACE VIEW published_price_observation AS
SELECT p.* FROM price_observation p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.status='review'
 AND (a.observed_on IS NULL OR a.observed_on=p.observed_on)
) AND NOT EXISTS (
 SELECT 1 FROM price_observation_review r
 WHERE r.document_id=p.document_id AND r.source_locator=p.source_locator
 AND r.product_id=p.product_id AND r.market_id=p.market_id AND r.source_id=p.source_id
 AND r.observed_on=p.observed_on AND r.period=p.period AND r.unit=p.unit
);
GRANT SELECT ON published_price_observation TO agro_reader;
