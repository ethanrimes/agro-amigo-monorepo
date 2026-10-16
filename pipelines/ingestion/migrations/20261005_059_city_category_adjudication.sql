-- STAGED TRACKED CANDIDATE, NOT APPLIED. Run as one migration transaction.
-- PRIVATE, REVIEW ONLY. Must be bound to frozen skip-only worker SHA e492493...
-- and run in the same owner transaction as the exact three resolutions.
DO $$
DECLARE prior text;
BEGIN
 SELECT pg_get_constraintdef(oid) INTO STRICT prior FROM pg_constraint
 WHERE conrelid='city_category_overlay_proof'::regclass
   AND conname='city_category_overlay_proof_parser_code_sha256_check'
   AND contype='c' AND convalidated;
 IF prior =
   'CHECK ((parser_code_sha256 = ''54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2''::text))'
 THEN
   ALTER TABLE city_category_overlay_proof
     DROP CONSTRAINT city_category_overlay_proof_parser_code_sha256_check;
   ALTER TABLE city_category_overlay_proof
     ADD CONSTRAINT city_category_overlay_proof_parser_code_sha256_check CHECK (
       parser_version='city-v8' AND parser_code_sha256 IN (
         '54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2',
         'e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0'
       )
     );
 ELSIF prior =
   'CHECK (((parser_version = ''city-v8''::text) AND (parser_code_sha256 = ANY (ARRAY[''54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2''::text, ''e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0''::text]))))'
 THEN NULL; -- Verified exact, validated previously applied migration.
 ELSE
   RAISE EXCEPTION 'City parser proof constraint is neither exact SQL057 nor reviewed SQL059';
 END IF;
END $$;
-- Existing old proof rows are never updated; future proofs bind the SHA of
-- their actual reviewed parser file and retain source-specific proof IDs.

-- PRIVATE PROPOSAL ONLY. Exact Sep 7 Corabastos adjudication after SQL058 and
-- reviewed worker C-order fix. Do not deploy without full human/SQL review.
-- This leaves immutable raw rows, source bytes and conflict rows untouched.
CREATE TABLE IF NOT EXISTS city_pdf_category_resolution (
 document_id text PRIMARY KEY REFERENCES source_document(id),
 conflict_id bigint NOT NULL UNIQUE REFERENCES city_pdf_publication_conflict(id),
 archive_id text NOT NULL REFERENCES source_document(id),
 entry_name text NOT NULL,
 source_url text NOT NULL,
 proof_id text NOT NULL CHECK (proof_id ~ '^[0-9a-f]{64}$'),
 parser_code_sha256 text NOT NULL,
 raw_rows_sha256 text NOT NULL,
 classification_sha256 text NOT NULL,
 member_checkpoint_step text NOT NULL,
 resolution_kind text NOT NULL CHECK (resolution_kind='reviewed-retained-pdf-category-only'),
 reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
-- Intentionally no INSERT grant to agro_ingestor or agro_reader. A separately
-- reviewed one-shot adjudicator must hold the owner privilege.
CREATE OR REPLACE FUNCTION validate_city_pdf_category_resolution()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE want record;
DECLARE conflict city_pdf_publication_conflict%ROWTYPE;
DECLARE child source_document%ROWTYPE;
DECLARE parent source_document%ROWTYPE;
DECLARE n_raw integer;
DECLARE n_class integer;
DECLARE n_changed integer;
DECLARE raw_hash text;
DECLARE class_hash text;
BEGIN
 SELECT * INTO want FROM (VALUES
  ('92da0fac7ad659cb73115d60efc07d66d72c0f77bc4a89490147226c828bda61',1::bigint,'Bol-Corabastos07sep26.pdf','bb7f4879f1ce021fa61015a267289dbdc8cd913f067eb85d607409254c5b05a7','3cb54db5a230e08dc872e5379eb4522d022a0efc8884f51a6a2d0b54aa5e4336','2e69045288701029aaae302b20b2ac990844939e391e4fe096687bc3d2d7b493','city-member:d282b5db1987b1c7eb4ec9a3d2c07c1eaab11506fbaf5b14f3137d60627885d0'),
  ('acd65fc551850af8883b86b02cd461b8f13a999657e1ff83d07ff5a1433dcc95',2::bigint,'Bogotá, D.C., Corabastos-07-09-2026.pdf','d83fe5fd51431b121ef6ebe6244da1be182411245491fa4084547e4371efd7e5','ee66f021589e7cf42806bd777f50a73e482a908b686062145f0d3f26bf423cf7','2e69045288701029aaae302b20b2ac990844939e391e4fe096687bc3d2d7b493','city-member:bbed9bf538638b6213bf125fd49fa27bc6e40bb780a3f11aee067556fe10ff91'),
  ('d0b02fdc617f8befed5d08a86a75a2878eb0de428f43ae4b867d42833e5225d7',3::bigint,'Bogotá, D.C., Corabastos-07-09-2026-1.pdf','42214c80e1a412f26a58f10181107f64a26b78acfcc301b9bfbde51b7a30644a','9e55007d0d76ddcd3d91084b5c1d1dca30aa3b102cc0dd070c734b301736e818','2e69045288701029aaae302b20b2ac990844939e391e4fe096687bc3d2d7b493','city-member:f01114709d81704ff4f8b9a0279e474cd6bbbd36c836c8e7ccb212f1e88bc3ef')
 ) AS expected(document_id,conflict_id,entry_name,proof_id,raw_hash,class_hash,step)
 WHERE expected.document_id=NEW.document_id;
 IF want.document_id IS NULL OR NEW.conflict_id IS DISTINCT FROM want.conflict_id
    OR NEW.entry_name IS DISTINCT FROM want.entry_name
    OR NEW.proof_id IS DISTINCT FROM want.proof_id
    OR NEW.raw_rows_sha256 IS DISTINCT FROM want.raw_hash
    OR NEW.classification_sha256 IS DISTINCT FROM want.class_hash
    OR NEW.member_checkpoint_step IS DISTINCT FROM want.step
    OR NEW.archive_id IS DISTINCT FROM '12994008dc0a233459abd4edc0cc4ffdb67b6bfcfd93423ed9abfbed1611d2af'
    OR NEW.source_url IS DISTINCT FROM 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-07sep2026.zip'
    OR NEW.parser_code_sha256 IS DISTINCT FROM '54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2'
 THEN RAISE EXCEPTION 'Unreviewed city category resolution identity'; END IF;
 SELECT * INTO conflict FROM city_pdf_publication_conflict WHERE id=NEW.conflict_id;
 SELECT * INTO child FROM source_document WHERE id=NEW.document_id;
 SELECT * INTO parent FROM source_document WHERE id=NEW.archive_id;
 IF conflict.document_id IS DISTINCT FROM NEW.document_id
    OR conflict.archive_id IS DISTINCT FROM NEW.archive_id
    OR conflict.entry_name IS DISTINCT FROM NEW.entry_name
    OR conflict.processor_version IS DISTINCT FROM 'city-v8'
    OR conflict.native_sha256 IS DISTINCT FROM '2063fd66580cde5f12bfa6feba540de2a06d7fb47da79c272e07fd40747e971a'
    OR conflict.stored_sha256 IS DISTINCT FROM '5f58119f0d0e1d7c682427f127f3bfa718618f2be3de0697063582dd00984a90'
    OR conflict.details->'difference_fields' IS DISTINCT FROM '["category"]'::jsonb
    OR conflict.details->>'difference_count' IS DISTINCT FROM '198'
    OR conflict.details->>'native_count' IS DISTINCT FROM '198'
    OR conflict.details->>'stored_count' IS DISTINCT FROM '198'
    OR conflict.details->>'classification_count' IS DISTINCT FROM '198'
    OR (SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)<>1
    OR child.kind IS DISTINCT FROM 'original' OR child.media_type IS DISTINCT FROM 'application/pdf'
    OR child.source_url IS DISTINCT FROM NEW.source_url
    OR encode(sha256(child.content),'hex') IS DISTINCT FROM NEW.document_id
    OR child.metadata->>'archive_entry' IS DISTINCT FROM NEW.entry_name
    OR NOT (child.metadata->'parents' ? NEW.archive_id)
    OR parent.kind IS DISTINCT FROM 'original' OR parent.media_type IS DISTINCT FROM 'application/zip'
    OR parent.source_url IS DISTINCT FROM NEW.source_url
    OR encode(sha256(parent.content),'hex') IS DISTINCT FROM NEW.archive_id
    OR NOT EXISTS (SELECT 1 FROM source_archive_member m WHERE m.archive_id=NEW.archive_id
                   AND m.entry_name=NEW.entry_name AND m.document_id=NEW.document_id)
    OR EXISTS (SELECT 1 FROM regional_price_category_overlay WHERE document_id=NEW.document_id)
    OR EXISTS (SELECT 1 FROM city_category_overlay_proof WHERE document_id=NEW.document_id)
    OR NOT EXISTS (SELECT 1 FROM ingestion_checkpoint cp WHERE cp.document_id=NEW.archive_id
      AND cp.processor_version='city-v8' AND cp.step=NEW.member_checkpoint_step AND cp.records=198)
 THEN RAISE EXCEPTION 'City category resolution lacks original/conflict/checkpoint proof'; END IF;
 SELECT count(*),count(c.source_locator),
        count(*) FILTER (WHERE r.category<>array_to_string(c.category_path,' > ')),
        encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.source_locator COLLATE "C")::text,'[]'),'UTF8')),'hex')
 INTO n_raw,n_class,n_changed,raw_hash
 FROM regional_price r LEFT JOIN regional_classification c
   ON c.document_id=r.document_id AND c.source_locator=r.source_locator
 WHERE r.document_id=NEW.document_id;
 SELECT encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_array(c.source_locator,c.category_path)
   ORDER BY c.source_locator COLLATE "C")::text,'[]'),'UTF8')),'hex')
 INTO class_hash FROM regional_classification c WHERE c.document_id=NEW.document_id;
 IF n_raw<>198 OR n_class<>198 OR n_changed<>198
    OR (SELECT count(*) FROM regional_classification WHERE document_id=NEW.document_id)<>198
    OR raw_hash IS DISTINCT FROM want.raw_hash OR class_hash IS DISTINCT FROM want.class_hash
 THEN RAISE EXCEPTION 'City category resolution raw/classification fingerprint drift'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_city_pdf_category_resolution ON city_pdf_category_resolution;
DROP TRIGGER IF EXISTS immutable_history ON city_pdf_category_resolution;
DROP TRIGGER IF EXISTS retain_history ON city_pdf_category_resolution;
CREATE TRIGGER validate_city_pdf_category_resolution BEFORE INSERT ON city_pdf_category_resolution
 FOR EACH ROW EXECUTE FUNCTION validate_city_pdf_category_resolution();
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_pdf_category_resolution
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_pdf_category_resolution
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();

-- A conflict remains visible forever; only the exact separately validated
-- resolution changes whether it is unresolved for read/skip purposes.
CREATE OR REPLACE VIEW verified_city_pdf_category_resolution AS
 SELECT a.* FROM city_pdf_category_resolution a WHERE EXISTS (
  SELECT 1 FROM ingestion_checkpoint cp WHERE cp.document_id=a.archive_id
   AND cp.processor_version='city-v8' AND cp.step=a.member_checkpoint_step
   AND cp.records=198);
CREATE OR REPLACE VIEW unresolved_city_pdf_publication_conflict AS
 SELECT c.* FROM city_pdf_publication_conflict c WHERE NOT EXISTS (
  SELECT 1 FROM verified_city_pdf_category_resolution a
  WHERE a.conflict_id=c.id AND a.document_id=c.document_id);
GRANT SELECT ON unresolved_city_pdf_publication_conflict TO agro_ingestor;
CREATE OR REPLACE VIEW published_regional_price AS
 SELECT r.* FROM regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM unresolved_city_pdf_publication_conflict c
  WHERE c.document_id=r.document_id OFFSET 0);
CREATE OR REPLACE VIEW verified_regional_category_overlay AS
 SELECT o.document_id,o.source_locator,o.corrected_category
 FROM regional_price_category_overlay o
 WHERE EXISTS (SELECT 1 FROM city_category_overlay_proof p
  WHERE p.document_id=o.document_id
    AND o.source_sha256=p.source_sha256 AND o.source_url=p.source_url
    AND o.locator_set_sha256=p.locator_set_sha256
    AND o.unchanged_fields_sha256=p.unchanged_fields_sha256
    AND o.native_rows_sha256=p.native_rows_sha256
    AND o.old_rows_sha256=p.old_rows_sha256)
 UNION ALL
 SELECT r.document_id,r.source_locator,array_to_string(c.category_path,' > ') AS corrected_category
 FROM verified_city_pdf_category_resolution a
 JOIN regional_price r ON r.document_id=a.document_id
 JOIN regional_classification c ON c.document_id=r.document_id
  AND c.source_locator=r.source_locator;
-- Existing resolved_regional_price view continues to use the verified overlay.
