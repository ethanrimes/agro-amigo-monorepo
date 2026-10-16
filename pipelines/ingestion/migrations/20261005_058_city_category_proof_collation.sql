-- Match the parser's Unicode codepoint ordering for the two proof digests.
-- Locale punctuation ordering can otherwise put "row 50" before "row 5".
-- All source, row, classification, overlay, and conflict guards remain intact.
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
          '' ORDER BY r.source_locator COLLATE "C"),''),'UTF8')),'hex'),
        encode(sha256(convert_to(coalesce(string_agg(
          length(r.source_locator)::text||':'||r.source_locator||
          length(array_to_string(c.category_path,' > '))::text||':'||
          array_to_string(c.category_path,' > '),
          '' ORDER BY r.source_locator COLLATE "C"),''),'UTF8')),'hex')
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
