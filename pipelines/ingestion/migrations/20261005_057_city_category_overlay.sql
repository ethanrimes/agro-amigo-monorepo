-- Append-only, exact-source city category proof. Keep raw quotes and originals immutable.
-- Retain regional_price and regional_classification unchanged. A finalized,
-- exact-source proof permits only a category-field projection at read time.

CREATE TABLE IF NOT EXISTS regional_price_category_overlay (
 document_id text NOT NULL,
 source_locator text NOT NULL,
 old_category text NOT NULL,
 corrected_category text NOT NULL,
 category_path text[] NOT NULL,
 literal_heading text NOT NULL,
 heading_rule text NOT NULL CHECK (
   heading_rule IN ('literal-leaf','verified-printed-leaf-capitalize')
 ),
 source_page integer NOT NULL CHECK (source_page>0),
 source_sha256 text NOT NULL CHECK (source_sha256=document_id),
 source_url text NOT NULL,
 unchanged_fields_sha256 text NOT NULL CHECK (unchanged_fields_sha256 ~ '^[0-9a-f]{64}$'),
 locator_set_sha256 text NOT NULL CHECK (locator_set_sha256 ~ '^[0-9a-f]{64}$'),
 native_rows_sha256 text NOT NULL CHECK (native_rows_sha256 ~ '^[0-9a-f]{64}$'),
 old_rows_sha256 text NOT NULL CHECK (old_rows_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,source_locator),
 FOREIGN KEY(document_id,source_locator) REFERENCES regional_price(document_id,source_locator),
 CHECK(old_category<>corrected_category),
 CHECK(cardinality(category_path)>=2),
 CHECK(corrected_category=array_to_string(category_path,' > ')),
 CHECK(old_category=category_path[cardinality(category_path)] OR
       (old_category=literal_heading AND heading_rule='verified-printed-leaf-capitalize'))
);

-- Insert a complete parser attestation LAST, in the same transaction as
-- first-time overlay rows. Later parser versions may append new attestations
-- only after exact full-source revalidation of the same immutable mapping.
CREATE TABLE IF NOT EXISTS city_category_overlay_proof (
 document_id text NOT NULL REFERENCES source_document(id),
 proof_id text NOT NULL CHECK(proof_id ~ '^[0-9a-f]{64}$'),
 archive_id text NOT NULL REFERENCES source_document(id),
 entry_name text NOT NULL,
 requested_entry_name text NOT NULL,
 source_sha256 text NOT NULL CHECK(source_sha256=document_id),
 source_url text NOT NULL,
 parser_version text NOT NULL CHECK(parser_version='city-v8'),
 parser_code_sha256 text NOT NULL CHECK(parser_code_sha256='54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2'),
 raw_row_count integer NOT NULL CHECK(raw_row_count>0),
 correction_count integer NOT NULL CHECK(correction_count>0 AND correction_count<=raw_row_count),
 locator_set_sha256 text NOT NULL CHECK(locator_set_sha256 ~ '^[0-9a-f]{64}$'),
 db_locator_set_sha256 text NOT NULL CHECK(db_locator_set_sha256 ~ '^[0-9a-f]{64}$'),
 db_classification_sha256 text NOT NULL CHECK(db_classification_sha256 ~ '^[0-9a-f]{64}$'),
 unchanged_fields_sha256 text NOT NULL CHECK(unchanged_fields_sha256 ~ '^[0-9a-f]{64}$'),
 native_rows_sha256 text NOT NULL CHECK(native_rows_sha256 ~ '^[0-9a-f]{64}$'),
 old_rows_sha256 text NOT NULL CHECK(old_rows_sha256 ~ '^[0-9a-f]{64}$'),
 verification jsonb NOT NULL CHECK(jsonb_typeof(verification)='object'
   AND verification->>'method'='retained-city-pdf-whole-source-category-only'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,proof_id)
);

-- Deterministic length-framed complete-plan identity, also computed by Python.
CREATE OR REPLACE FUNCTION city_category_proof_id(parts text[])
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT encode(sha256(convert_to(coalesce(string_agg(length(value)::text||':'||value,
   '' ORDER BY ordinal),'') ,'UTF8')),'hex')
 FROM unnest(parts) WITH ORDINALITY AS item(value,ordinal)
$$;

CREATE OR REPLACE FUNCTION validate_regional_category_overlay()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE raw regional_price%ROWTYPE;
DECLARE path text[];
DECLARE source source_document%ROWTYPE;
BEGIN
 SELECT * INTO raw FROM regional_price
 WHERE document_id=NEW.document_id AND source_locator=NEW.source_locator;
 SELECT category_path INTO path FROM regional_classification
 WHERE document_id=NEW.document_id AND source_locator=NEW.source_locator;
 SELECT * INTO source FROM source_document WHERE id=NEW.document_id;
 IF EXISTS(SELECT 1 FROM city_category_overlay_proof WHERE document_id=NEW.document_id) THEN
  RAISE EXCEPTION 'A finalized category proof cannot acquire another overlay row';
 END IF;
 IF raw.document_id IS NULL OR source.id IS NULL
    OR source.kind<>'original'
    OR source.media_type<>'application/pdf'
    OR encode(sha256(source.content),'hex') IS DISTINCT FROM NEW.source_sha256
    OR source.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-pdf'
    OR source.source_url IS DISTINCT FROM NEW.source_url
    OR raw.category IS DISTINCT FROM NEW.old_category
    OR raw.source_page IS DISTINCT FROM NEW.source_page
    OR path IS DISTINCT FROM NEW.category_path
    OR source.metadata->>'archive_entry' IS NULL
    OR EXISTS(SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Category overlay lacks exact retained city row/source/classification';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_city_category_overlay ON regional_price_category_overlay;
CREATE TRIGGER validate_city_category_overlay BEFORE INSERT ON regional_price_category_overlay
 FOR EACH ROW EXECUTE FUNCTION validate_regional_category_overlay();

CREATE OR REPLACE FUNCTION validate_city_category_overlay_proof()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source source_document%ROWTYPE;
DECLARE parent source_document%ROWTYPE;
DECLARE n_raw integer;
DECLARE n_classified integer;
DECLARE n_changed integer;
DECLARE n_overlay integer;
DECLARE db_locators text;
DECLARE db_classifications text;
BEGIN
 SELECT * INTO source FROM source_document WHERE id=NEW.document_id;
 SELECT * INTO parent FROM source_document WHERE id=NEW.archive_id;
 SELECT count(*),count(c.source_locator),
        count(*) FILTER (WHERE r.category<>array_to_string(c.category_path,' > ')),
        encode(sha256(convert_to(coalesce(string_agg(
          length(r.source_locator)::text||':'||r.source_locator,
          '' ORDER BY r.source_locator),''),'UTF8')),'hex'),
        encode(sha256(convert_to(coalesce(string_agg(
          length(r.source_locator)::text||':'||r.source_locator||
          length(array_to_string(c.category_path,' > '))::text||':'||
          array_to_string(c.category_path,' > '),
          '' ORDER BY r.source_locator),''),'UTF8')),'hex')
 INTO n_raw,n_classified,n_changed,db_locators,db_classifications
 FROM regional_price r LEFT JOIN regional_classification c
   ON c.document_id=r.document_id AND c.source_locator=r.source_locator
 WHERE r.document_id=NEW.document_id;
 SELECT count(*) INTO n_overlay FROM regional_price_category_overlay
 WHERE document_id=NEW.document_id
   AND source_sha256=NEW.source_sha256 AND source_url=NEW.source_url
   AND locator_set_sha256=NEW.locator_set_sha256
   AND unchanged_fields_sha256=NEW.unchanged_fields_sha256
   AND native_rows_sha256=NEW.native_rows_sha256
   AND old_rows_sha256=NEW.old_rows_sha256;
 IF NEW.proof_id IS DISTINCT FROM city_category_proof_id(ARRAY[
       NEW.archive_id,NEW.entry_name,NEW.requested_entry_name,
       NEW.source_sha256,NEW.source_url,
       NEW.parser_version,NEW.parser_code_sha256,NEW.raw_row_count::text,
       NEW.correction_count::text,NEW.locator_set_sha256,NEW.db_locator_set_sha256,
       NEW.db_classification_sha256,NEW.unchanged_fields_sha256,
       NEW.native_rows_sha256,NEW.old_rows_sha256])
    OR source.id IS NULL OR source.kind<>'original' OR source.media_type<>'application/pdf' 
    OR encode(sha256(source.content),'hex') IS DISTINCT FROM NEW.source_sha256
    OR parent.id IS NULL OR parent.kind<>'original' OR parent.media_type<>'application/zip'
    OR encode(sha256(parent.content),'hex') IS DISTINCT FROM NEW.archive_id
    OR parent.source_url IS DISTINCT FROM NEW.source_url
    OR source.source_url IS DISTINCT FROM NEW.source_url
    OR source.metadata->>'archive_entry' IS DISTINCT FROM NEW.entry_name
    OR NOT (source.metadata->'parents' ? NEW.archive_id)
    OR NOT EXISTS (SELECT 1 FROM source_archive_member m WHERE m.archive_id=NEW.archive_id
                   AND m.entry_name=NEW.entry_name AND m.document_id=NEW.document_id)
    OR NOT EXISTS (SELECT 1 FROM source_archive_member m WHERE m.archive_id=NEW.archive_id
                   AND m.entry_name=NEW.requested_entry_name AND m.document_id=NEW.document_id)
    OR n_raw<>NEW.raw_row_count OR n_classified<>n_raw
    OR n_changed<>NEW.correction_count OR n_overlay<>NEW.correction_count
    OR db_locators IS DISTINCT FROM NEW.db_locator_set_sha256
    OR db_classifications IS DISTINCT FROM NEW.db_classification_sha256
    OR EXISTS (SELECT 1 FROM regional_price r JOIN regional_classification c
               USING(document_id,source_locator)
               WHERE r.document_id=NEW.document_id
                 AND r.category<>array_to_string(c.category_path,' > ')
                 AND NOT EXISTS (SELECT 1 FROM regional_price_category_overlay o
                   WHERE o.document_id=r.document_id AND o.source_locator=r.source_locator))
    OR EXISTS (SELECT 1 FROM regional_price_category_overlay o
               JOIN regional_price r USING(document_id,source_locator)
               JOIN regional_classification c USING(document_id,source_locator)
               WHERE o.document_id=NEW.document_id
                 AND r.category=array_to_string(c.category_path,' > '))
    OR EXISTS(SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Whole-city category proof is incomplete or source identity differs';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_city_category_overlay_proof ON city_category_overlay_proof;
CREATE TRIGGER validate_city_category_overlay_proof BEFORE INSERT ON city_category_overlay_proof
 FOR EACH ROW EXECUTE FUNCTION validate_city_category_overlay_proof();

-- The existing retention helper blocks UPDATE/DELETE/TRUNCATE. The exact
-- source/original and per-row proof must remain append-only after insertion.
DROP TRIGGER IF EXISTS immutable_history ON regional_price_category_overlay;
DROP TRIGGER IF EXISTS immutable_history ON city_category_overlay_proof;
CREATE TRIGGER immutable_history BEFORE UPDATE ON regional_price_category_overlay
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON regional_price_category_overlay;
DROP TRIGGER IF EXISTS retain_history ON city_category_overlay_proof;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON regional_price_category_overlay
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_category_overlay_proof
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_category_overlay_proof
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON regional_price_category_overlay,city_category_overlay_proof TO agro_ingestor;
GRANT SELECT ON regional_price_category_overlay,city_category_overlay_proof TO agro_reader;

-- Only rows attached to the finalized exact-source proof can affect a read.
-- An unfinalized/orphan overlay remains inert.
CREATE OR REPLACE VIEW verified_regional_category_overlay AS
 SELECT o.document_id,o.source_locator,o.corrected_category
 FROM regional_price_category_overlay o
 WHERE EXISTS (SELECT 1 FROM city_category_overlay_proof p
  WHERE p.document_id=o.document_id
    AND o.source_sha256=p.source_sha256 AND o.source_url=p.source_url
   AND o.locator_set_sha256=p.locator_set_sha256
   AND o.unchanged_fields_sha256=p.unchanged_fields_sha256
   AND o.native_rows_sha256=p.native_rows_sha256
   AND o.old_rows_sha256=p.old_rows_sha256);
GRANT SELECT ON verified_regional_category_overlay TO agro_reader;

-- Retain the existing UNION ALL product-ID seek shape and conflict gate.
-- published_regional_price remains unchanged and still excludes unresolved
-- city_pdf_publication_conflict rows. Category projection applies in both
-- original-ID and audited product-name-correction branches.
CREATE OR REPLACE VIEW resolved_regional_price AS
 SELECT r.document_id,r.source_locator,r.observed_on,
  r.product_id,r.product_name,r.market_name,
  coalesce(o.corrected_category,r.category) AS category,
  r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
 FROM published_regional_price r
 LEFT JOIN verified_regional_category_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator
 WHERE NOT EXISTS (
  SELECT 1 FROM regional_price_product_correction c
  WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator
 )
 UNION ALL
 SELECT r.document_id,r.source_locator,r.observed_on,
  c.corrected_product_id AS product_id,c.corrected_product_name AS product_name,
  r.market_name,coalesce(o.corrected_category,r.category) AS category,
  r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r
  ON r.document_id=c.document_id AND r.source_locator=c.source_locator
 LEFT JOIN verified_regional_category_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator;
GRANT SELECT ON resolved_regional_price TO agro_reader;

-- In city_reports._publication_parity, compare raw leaf *and* proven overlay:
-- when proof exists and all source/version/digest fields match the freshly
-- computed whole-source plan, treat only category as corrected. Existing
-- product_id/product_name correction logic stays independent. The final
-- require_all pass still checks every locator and all other typed fields.
