-- Preserve the prior review decision when a complete, cached, typed OCR pair
-- is requeued under the narrowly scoped agreement policy. This table is
-- append-only; no source document, image, reading or prior quote is changed.
CREATE TABLE IF NOT EXISTS source_ocr_review_history (
 document_id text NOT NULL REFERENCES source_document(id),
 source_locator text NOT NULL,
 policy_version text NOT NULL,
 source_kind text NOT NULL,
 prior_status text NOT NULL,
 prior_error text,
 reading0_sha256 text NOT NULL CHECK(reading0_sha256 ~ '^[0-9a-f]{64}$'),
 reading1_sha256 text NOT NULL CHECK(reading1_sha256 ~ '^[0-9a-f]{64}$'),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,policy_version)
);
DROP TRIGGER IF EXISTS retain_history ON source_ocr_review_history;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON source_ocr_review_history
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON source_ocr_review_history;
CREATE TRIGGER immutable_history BEFORE UPDATE ON source_ocr_review_history
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON source_ocr_review_history TO agro_ingestor;
GRANT SELECT ON source_ocr_review_history TO agro_reader;
