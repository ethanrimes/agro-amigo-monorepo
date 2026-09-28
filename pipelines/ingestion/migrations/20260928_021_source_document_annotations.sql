-- Append display corrections without modifying immutable source metadata/bytes.
CREATE TABLE IF NOT EXISTS source_document_annotation (
 annotation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 field text NOT NULL CHECK(field='reference_period'),
 original_value text NOT NULL,
 corrected_value text NOT NULL CHECK(btrim(corrected_value)<>''),
 reason text NOT NULL CHECK(btrim(reason)<>''),
 native_locators text[] NOT NULL CHECK(cardinality(native_locators)>0
   AND array_position(native_locators,NULL) IS NULL),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(document_id,field,corrected_value,reason,native_locators)
);
CREATE INDEX IF NOT EXISTS source_document_annotation_latest
 ON source_document_annotation(document_id,field,annotation_id DESC);
CREATE OR REPLACE FUNCTION validate_source_document_annotation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE original_period text;
BEGIN
 IF NEW.field<>'reference_period' THEN
  RAISE EXCEPTION 'Unsupported source metadata annotation field';
 END IF;
 SELECT reference_period INTO original_period FROM source_document WHERE id=NEW.document_id;
 IF NOT FOUND OR NEW.original_value IS DISTINCT FROM original_period THEN
  RAISE EXCEPTION 'Annotation must identify the exact immutable original value';
 END IF;
 IF EXISTS(SELECT 1 FROM unnest(NEW.native_locators) locator WHERE btrim(locator)='') THEN
  RAISE EXCEPTION 'Annotation requires nonempty native source locators';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_annotation ON source_document_annotation;
CREATE TRIGGER validate_annotation BEFORE INSERT ON source_document_annotation
 FOR EACH ROW EXECUTE FUNCTION validate_source_document_annotation();
DROP TRIGGER IF EXISTS immutable_history ON source_document_annotation;
CREATE TRIGGER immutable_history BEFORE UPDATE ON source_document_annotation
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON source_document_annotation;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON source_document_annotation
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON source_document_annotation TO agro_reader;
GRANT SELECT,INSERT ON source_document_annotation TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE source_document_annotation_annotation_id_seq TO agro_ingestor;
