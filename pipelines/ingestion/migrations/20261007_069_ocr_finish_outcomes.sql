-- Future OCR attempts retain only a sanitized provider outcome. Historical
-- attempts/results/reviews remain byte-for-byte unchanged and unclassified.
ALTER TABLE source_ocr_attempt
  ADD COLUMN IF NOT EXISTS version text,
  ADD COLUMN IF NOT EXISTS reading smallint;
ALTER TABLE source_ocr_attempt
  DROP CONSTRAINT IF EXISTS source_ocr_attempt_reading_valid;
ALTER TABLE source_ocr_attempt
  ADD CONSTRAINT source_ocr_attempt_reading_valid
  CHECK (reading IS NULL OR reading IN (0, 1));

CREATE INDEX IF NOT EXISTS source_ocr_attempt_reading_history
  ON source_ocr_attempt(image_id, version, reading, id)
  WHERE version IS NOT NULL;

CREATE TABLE IF NOT EXISTS source_ocr_attempt_outcome (
  attempt_id bigint PRIMARY KEY REFERENCES source_ocr_attempt(id),
  outcome_code text NOT NULL CHECK (outcome_code IN (
    'STOP_VALID', 'MAX_TOKENS', 'SAFETY', 'RECITATION', 'BLOCKLIST',
    'PROHIBITED_CONTENT', 'NO_CANDIDATE', 'OTHER_FINISH',
    'MALFORMED_RESPONSE', 'STOP_BAD_JSON', 'STOP_BAD_SCHEMA',
    'HTTP_429', 'HTTP_RETRYABLE', 'HTTP_ERROR', 'NETWORK_ERROR'
  )),
  recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION validate_source_ocr_attempt_outcome() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM source_ocr_attempt a WHERE a.id=NEW.attempt_id
      AND a.version IS NOT NULL AND a.reading IN (0, 1)
  ) THEN
    RAISE EXCEPTION 'OCR outcome requires a versioned reading attempt';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS valid_reading_attempt ON source_ocr_attempt_outcome;
CREATE TRIGGER valid_reading_attempt BEFORE INSERT ON source_ocr_attempt_outcome
  FOR EACH ROW EXECUTE FUNCTION validate_source_ocr_attempt_outcome();
DROP TRIGGER IF EXISTS retain_history ON source_ocr_attempt_outcome;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON source_ocr_attempt_outcome
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON source_ocr_attempt_outcome;
CREATE TRIGGER immutable_history BEFORE UPDATE ON source_ocr_attempt_outcome
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON source_ocr_attempt_outcome TO agro_ingestor;
GRANT SELECT ON source_ocr_attempt_outcome TO agro_reader;
