-- PRIVATE CANDIDATE ONLY. Extend the existing source-bound category overlay to
-- represent a literal top-level printed group without rewriting base history.
-- This migration does not insert evidence or change regional_price/classes.
DO $$
DECLARE c record;
BEGIN
  ALTER TABLE regional_price_category_overlay
    DROP CONSTRAINT IF EXISTS regional_price_category_overlay_path_nonempty_check,
    DROP CONSTRAINT IF EXISTS regional_price_category_overlay_heading_rule_check,
    DROP CONSTRAINT IF EXISTS regional_price_category_overlay_heading_shape_check,
    DROP CONSTRAINT IF EXISTS regional_price_category_overlay_top_level_source_scope_check;
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid='regional_price_category_overlay'::regclass
      AND contype='c'
      AND pg_get_constraintdef(oid) LIKE '%cardinality(category_path)%'
  LOOP
    EXECUTE format('ALTER TABLE regional_price_category_overlay DROP CONSTRAINT %I', c.conname);
  END LOOP;

  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid='regional_price_category_overlay'::regclass
      AND contype='c'
      AND pg_get_constraintdef(oid) LIKE '%heading_rule%'
  LOOP
    EXECUTE format('ALTER TABLE regional_price_category_overlay DROP CONSTRAINT %I', c.conname);
  END LOOP;

  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid='regional_price_category_overlay'::regclass
      AND contype='c'
      AND pg_get_constraintdef(oid) LIKE '%old_category%'
      AND pg_get_constraintdef(oid) LIKE '%literal_heading%'
  LOOP
    EXECUTE format('ALTER TABLE regional_price_category_overlay DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $$;

ALTER TABLE regional_price_category_overlay
  ADD CONSTRAINT regional_price_category_overlay_path_nonempty_check
    CHECK (cardinality(category_path)>=1),
  ADD CONSTRAINT regional_price_category_overlay_heading_rule_check
    CHECK (heading_rule IN (
      'literal-leaf',
      'verified-printed-leaf-capitalize',
      'literal-top-level-heading'
    )),
  ADD CONSTRAINT regional_price_category_overlay_heading_shape_check
    CHECK (
      corrected_category=array_to_string(category_path,' > ')
      AND (
        (heading_rule='literal-leaf'
          AND old_category=category_path[cardinality(category_path)])
        OR (heading_rule='verified-printed-leaf-capitalize'
          AND old_category=literal_heading)
        OR (heading_rule='literal-top-level-heading'
          AND cardinality(category_path)=1
          AND literal_heading=corrected_category)
      )
    ),
  ADD CONSTRAINT regional_price_category_overlay_top_level_source_scope_check
    CHECK (
      heading_rule <> 'literal-top-level-heading'
      OR document_id IN (
        '1d8258d2fa8f22a4c7bee56e03513fa6fc80e81f7c3149caa896c89deeebfcae',
        '7872936c55b88d539388b2f27865f5866dedb97a362f2223095629d811e3930c',
        'b262c47141d6b44d1e37b0a526405f79374ce017999fe1f36facd818d7816c57',
        '4ced8283b62ced0ffbf1cdb91e545a810fa2da4b13af52b2287594f547565078',
        '298f734fe2b12f4ed4ee8c9cc35541916a30d76926a36c22e83dcbf377d16c0c'
      )
    );

-- Preserve prior parser attestations and admit only the exact reviewed candidate
-- parser code hash. The parent ZIP/member/source proofs remain enforced.
DO $$
DECLARE prior text;
BEGIN
  SELECT pg_get_constraintdef(oid) INTO STRICT prior
  FROM pg_constraint
  WHERE conrelid='city_category_overlay_proof'::regclass
    AND conname='city_category_overlay_proof_parser_code_sha256_check'
    AND contype='c' AND convalidated;
  IF prior NOT LIKE '%54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2%'
     OR prior NOT LIKE '%e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0%'
  THEN
    RAISE EXCEPTION 'Unexpected prior city category parser attestation constraint: %', prior;
  END IF;
  ALTER TABLE city_category_overlay_proof
    DROP CONSTRAINT city_category_overlay_proof_parser_code_sha256_check;
  ALTER TABLE city_category_overlay_proof
    ADD CONSTRAINT city_category_overlay_proof_parser_code_sha256_check
    CHECK (parser_version='city-v8' AND parser_code_sha256 IN (
      '54f471ba1e592eb664de0e98266c511083031fdbd7ec8539df6b26a02adc12a2',
      'e492493f04acb1c3179418b2880b4adba5b7d3791b041eaffbdbfaf4b41a2bf0',
      '7843aef0fecca8b46978fa1753c36072068e4c1cc156fdb4a88abf40d4cec952'
    ));
END $$;


-- Replace row and whole-source proof validators for top-level source groups.
CREATE OR REPLACE FUNCTION validate_regional_category_overlay()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 raw regional_price%ROWTYPE;
 path text[];
 source source_document%ROWTYPE;
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
    OR (NEW.heading_rule='literal-top-level-heading'
        AND path IS DISTINCT FROM string_to_array(raw.category,' > '))
    OR (NEW.heading_rule<>'literal-top-level-heading'
        AND path IS DISTINCT FROM NEW.category_path)
    OR source.metadata->>'archive_entry' IS NULL
    OR EXISTS(SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Category overlay lacks exact retained city row/source/classification';
 END IF;
 RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION validate_city_category_overlay_proof()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 source source_document%ROWTYPE;
 parent source_document%ROWTYPE;
 n_raw integer;
 n_classified integer;
 n_changed integer;
 n_overlay integer;
 db_locators text;
 db_classifications text;
BEGIN
 SELECT * INTO source FROM source_document WHERE id=NEW.document_id;
 SELECT * INTO parent FROM source_document WHERE id=NEW.archive_id;
 SELECT count(*),count(c.source_locator),
        count(*) FILTER (WHERE r.category<>coalesce(o.corrected_category,
          array_to_string(c.category_path,' > '))),
        encode(sha256(convert_to(coalesce(string_agg(
          length(r.source_locator)::text||':'||r.source_locator,
          '' ORDER BY r.source_locator COLLATE "C"),''),'UTF8')),'hex'),
        encode(sha256(convert_to(coalesce(string_agg(
          length(r.source_locator)::text||':'||r.source_locator||
          length(array_to_string(c.category_path,' > '))::text||':'||
          array_to_string(c.category_path,' > '),
          '' ORDER BY r.source_locator COLLATE "C"),''),'UTF8')),'hex')
 INTO n_raw,n_classified,n_changed,db_locators,db_classifications
 FROM regional_price r LEFT JOIN regional_classification c
   ON c.document_id=r.document_id AND c.source_locator=r.source_locator
 LEFT JOIN regional_price_category_overlay o
   ON o.document_id=r.document_id AND o.source_locator=r.source_locator
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
                 AND NOT EXISTS (SELECT 1 FROM regional_price_category_overlay missing
                   WHERE missing.document_id=r.document_id AND missing.source_locator=r.source_locator))
    OR EXISTS (SELECT 1 FROM regional_price_category_overlay o
               JOIN regional_price r USING(document_id,source_locator)
               JOIN regional_classification c USING(document_id,source_locator)
               WHERE o.document_id=NEW.document_id
                 AND o.corrected_category=r.category)
    OR EXISTS(SELECT 1 FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Whole-city category proof is incomplete or source identity differs';
 END IF;
 RETURN NEW;
END $$;
