-- A parser upgrade must not certify or serve an immutable city PDF row that
-- disagrees with the newly parsed native source. Evidence is append-only and
-- scoped to the PDF child, never its ZIP siblings.
CREATE TABLE IF NOT EXISTS city_pdf_publication_conflict (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 archive_id text REFERENCES source_document(id),
 entry_name text,
 processor_version text NOT NULL,
 native_sha256 text NOT NULL CHECK (native_sha256 ~ '^[0-9a-f]{64}$'),
 stored_sha256 text NOT NULL CHECK (stored_sha256 ~ '^[0-9a-f]{64}$'),
 details jsonb NOT NULL CHECK (jsonb_typeof(details)='object'),
 detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(document_id,processor_version,native_sha256,stored_sha256)
);
CREATE INDEX IF NOT EXISTS city_pdf_publication_conflict_document
 ON city_pdf_publication_conflict(document_id);
DROP TRIGGER IF EXISTS immutable_history ON city_pdf_publication_conflict;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_pdf_publication_conflict
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_pdf_publication_conflict;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_pdf_publication_conflict
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_pdf_publication_conflict TO agro_reader;
GRANT SELECT,INSERT ON city_pdf_publication_conflict TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE city_pdf_publication_conflict_id_seq TO agro_ingestor;

-- Keep raw rows forever. An unresolved conflict blocks only its PDF document,
-- including obsolete locators that a newer parser no longer emits.
CREATE OR REPLACE VIEW published_regional_price AS
 SELECT r.* FROM regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM city_pdf_publication_conflict conflict
  WHERE conflict.document_id=r.document_id OFFSET 0
 );
GRANT SELECT ON published_regional_price TO agro_reader;

-- Preserve existing product-name corrections, but apply them only to rows
-- eligible for publication. No price/quantity/date/round changes are inferred.
CREATE OR REPLACE VIEW resolved_regional_price AS
 SELECT r.* FROM published_regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM regional_price_product_correction c
  WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator
 )
 UNION ALL
 SELECT r.document_id,r.source_locator,r.observed_on,
  c.corrected_product_id AS product_id,c.corrected_product_name AS product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,
  r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,
  r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r
  ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
GRANT SELECT ON resolved_regional_price TO agro_reader;
