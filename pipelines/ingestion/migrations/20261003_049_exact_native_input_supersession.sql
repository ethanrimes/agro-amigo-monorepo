-- Exact source-backed duplicate corrections preserve every original/raw row.
-- The ledger remains empty until an independently verified manifest is applied.
CREATE TABLE IF NOT EXISTS input_projection_supersession (
 old_document_id text NOT NULL REFERENCES source_document(id),
 old_source_locator text NOT NULL,
 old_id text NOT NULL,
 department text NOT NULL,
 observed_on date NOT NULL,
 name text NOT NULL,
 presentation text NOT NULL,
 price numeric NOT NULL,
 old_brand text NOT NULL,
 old_registration text NOT NULL,
 product_line text NOT NULL,
 replacement_document_id text NOT NULL REFERENCES source_document(id),
 replacement_source_locator text NOT NULL,
 replacement_id text NOT NULL,
 native_brand text NOT NULL CHECK (native_brand<>''),
 native_registration text NOT NULL CHECK (native_registration<>''),
 native_cells jsonb NOT NULL,
 reason text NOT NULL CHECK (reason<>''),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(old_document_id,old_source_locator,old_id,department,observed_on),
 CHECK(old_document_id<>replacement_document_id),
 CHECK(old_id<>replacement_id)
);
CREATE INDEX IF NOT EXISTS input_projection_supersession_old_id
 ON input_projection_supersession(old_id,department,observed_on);
-- Use existing immutable trigger function, as for input_identity_alias.
DROP TRIGGER IF EXISTS retain_history ON input_projection_supersession;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON input_projection_supersession
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON input_projection_supersession;
CREATE TRIGGER immutable_history BEFORE UPDATE ON input_projection_supersession
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON input_projection_supersession TO agro_ingestor;
GRANT SELECT ON input_projection_supersession TO agro_reader;

-- An insert changes publication without changing the physical input_price
-- rows. Advance the department epoch and record every affected old/current ID
-- in the SAME transaction. The existing v047 delta overlay then reads these
-- IDs directly while the materialized raw pointer is stale; v048 refresh may
-- rebuild later without a correctness gap. No municipal scope is affected.
CREATE OR REPLACE FUNCTION input_projection_supersession_changed() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE next_epoch bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM new_rows) THEN RETURN NULL; END IF;
  UPDATE public.input_latest_projection_state SET source_epoch=source_epoch+1
  WHERE scope='department' RETURNING source_epoch INTO next_epoch;
  IF next_epoch IS NULL THEN RAISE EXCEPTION 'Missing department projection state'; END IF;
  INSERT INTO public.input_latest_projection_delta(scope,id,changed_epoch)
  SELECT DISTINCT 'department',id,next_epoch FROM (
    SELECT old_id AS id FROM new_rows
    UNION SELECT replacement_id AS id FROM new_rows
  ) affected WHERE true
  ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=greatest(
    input_latest_projection_delta.changed_epoch,excluded.changed_epoch);
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS input_supersession_projection_insert ON input_projection_supersession;
CREATE TRIGGER input_supersession_projection_insert
 AFTER INSERT ON input_projection_supersession REFERENCING NEW TABLE AS new_rows
 FOR EACH STATEMENT EXECUTE FUNCTION input_projection_supersession_changed();
REVOKE ALL ON FUNCTION input_projection_supersession_changed() FROM PUBLIC;


-- Preserve both current publication predicates verbatim, then append the
-- reviewed exact-cell supersession predicate.
CREATE OR REPLACE VIEW published_input_price AS
SELECT p.* FROM input_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
) AND NOT EXISTS (
 SELECT 1 FROM input_identity_alias a JOIN input_price replacement ON replacement.id=a.id
 WHERE a.legacy_id=p.id AND replacement.department=p.department
 AND replacement.observed_on=p.observed_on
 AND (replacement.name,replacement.presentation,replacement.brand,replacement.registration,replacement.product_line)
   IS NOT DISTINCT FROM (p.name,p.presentation,p.brand,p.registration,p.product_line)
 AND (SELECT retrieved_at FROM source_document WHERE id=replacement.document_id)
   >= (SELECT retrieved_at FROM source_document WHERE id=p.document_id)
)
AND NOT EXISTS (
 SELECT 1 FROM input_projection_supersession s
 JOIN input_price replacement ON replacement.id=s.replacement_id
  AND replacement.department=s.department
  AND replacement.observed_on=s.observed_on
  AND replacement.document_id=s.replacement_document_id
  AND replacement.source_locator=s.replacement_source_locator
 JOIN source_document old_doc ON old_doc.id=s.old_document_id
 JOIN source_document new_doc ON new_doc.id=s.replacement_document_id
 WHERE p.document_id=s.old_document_id
  AND p.source_locator=s.old_source_locator
  AND p.id=s.old_id
  AND p.department=s.department
  AND p.observed_on=s.observed_on
  AND (p.name,p.presentation,p.price,p.brand,p.registration,p.product_line)
    IS NOT DISTINCT FROM
      (s.name,s.presentation,s.price,s.old_brand,s.old_registration,s.product_line)
  AND (replacement.name,replacement.presentation,replacement.price,
       replacement.brand,replacement.registration,replacement.product_line)
    IS NOT DISTINCT FROM
      (s.name,s.presentation,s.price,s.native_brand,s.native_registration,s.product_line)
  AND old_doc.source_url=new_doc.source_url
  AND new_doc.retrieved_at>=old_doc.retrieved_at
);
GRANT SELECT ON published_input_price TO agro_reader;

