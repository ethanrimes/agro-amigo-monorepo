-- Migration 078: DANE city accepted-cohort publication and bounded page rotation.
-- Derived from the qualified O5/O6/prior-year private SQL inputs; 077 remains unchanged.

-- 078 prerequisite: monthly-page observations and refresh request/attempt evidence.
-- This schema was previously private-only; it is now included so 078 applies to maintained 077 alone.
CREATE TABLE IF NOT EXISTS dane_city_page_snapshot (
  snapshot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  page_url text NOT NULL,
  page_sha256 text NOT NULL CHECK (page_sha256 ~ '^[a-f0-9]{64}$'),
  page_bytes bytea NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS dane_city_page_snapshot_latest
  ON dane_city_page_snapshot(page_url,captured_at DESC,snapshot_id DESC);

CREATE TABLE IF NOT EXISTS dane_city_page_row (
  snapshot_id bigint NOT NULL REFERENCES dane_city_page_snapshot(snapshot_id),
  source_url text NOT NULL,
  observed_on date NOT NULL,
  row_date_label text NOT NULL,
  archive_label text NOT NULL,
  row_signature text NOT NULL CHECK (row_signature ~ '^[a-f0-9]{64}$'),
  PRIMARY KEY(snapshot_id,source_url)
);
CREATE INDEX IF NOT EXISTS dane_city_page_row_exact_source
  ON dane_city_page_row(source_url,snapshot_id DESC);

CREATE TABLE IF NOT EXISTS dane_city_refresh_request (
  request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  from_snapshot_id bigint NOT NULL REFERENCES dane_city_page_snapshot(snapshot_id),
  to_snapshot_id bigint NOT NULL REFERENCES dane_city_page_snapshot(snapshot_id),
  source_url text NOT NULL,
  observed_on date NOT NULL,
  old_signature text NOT NULL CHECK (old_signature ~ '^[a-f0-9]{64}$'),
  new_signature text NOT NULL CHECK (new_signature ~ '^[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(from_snapshot_id,to_snapshot_id,source_url),
  CHECK (from_snapshot_id<>to_snapshot_id),
  CHECK (old_signature<>new_signature)
);
CREATE INDEX IF NOT EXISTS dane_city_refresh_request_order ON dane_city_refresh_request(created_at,request_id);

-- Periodic same-URL byte checks are distinct from publisher-row-label hints.
ALTER TABLE dane_city_refresh_request
  ADD COLUMN IF NOT EXISTS request_reason text NOT NULL DEFAULT 'label_change';
ALTER TABLE dane_city_refresh_request ALTER COLUMN from_snapshot_id DROP NOT NULL;
ALTER TABLE dane_city_refresh_request ALTER COLUMN to_snapshot_id DROP NOT NULL;
ALTER TABLE dane_city_refresh_request ALTER COLUMN old_signature DROP NOT NULL;
ALTER TABLE dane_city_refresh_request ALTER COLUMN new_signature DROP NOT NULL;
DO $$ DECLARE con record; BEGIN
  FOR con IN SELECT conname FROM pg_constraint
    WHERE conrelid='dane_city_refresh_request'::regclass AND contype='c'
      AND (pg_get_constraintdef(oid) LIKE '%from_snapshot_id%'
           OR pg_get_constraintdef(oid) LIKE '%old_signature%'
           OR conname IN ('dane_city_refresh_request_reason_check',
                          'dane_city_refresh_request_source_hint_check'))
  LOOP EXECUTE format('ALTER TABLE dane_city_refresh_request DROP CONSTRAINT %I',con.conname); END LOOP;
END $$;
ALTER TABLE dane_city_refresh_request
  ADD CONSTRAINT dane_city_refresh_request_reason_check
  CHECK (request_reason IN ('label_change','periodic_byte_verification',
                            'worker_observed_body_change')),
  ADD CONSTRAINT dane_city_refresh_request_source_hint_check
  CHECK ((request_reason='label_change' AND from_snapshot_id IS NOT NULL
          AND to_snapshot_id IS NOT NULL AND old_signature IS NOT NULL
          AND new_signature IS NOT NULL AND from_snapshot_id<>to_snapshot_id
          AND old_signature<>new_signature)
      OR (request_reason IN ('periodic_byte_verification','worker_observed_body_change')
          AND from_snapshot_id IS NULL AND to_snapshot_id IS NULL
          AND old_signature IS NULL AND new_signature IS NULL));

CREATE TABLE IF NOT EXISTS dane_city_refresh_attempt (
  request_id bigint NOT NULL REFERENCES dane_city_refresh_request(request_id),
  attempt_no integer NOT NULL CHECK (attempt_no>0),
  outcome text NOT NULL CHECK (outcome IN ('unchanged','published','failed','held')),
  attempted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  next_attempt_at timestamptz,
  fetched_sha256 text CHECK (fetched_sha256 IS NULL OR fetched_sha256 ~ '^[a-f0-9]{64}$'),
  error text,
  PRIMARY KEY(request_id,attempt_no),
  CHECK ((outcome IN ('failed','held') AND next_attempt_at IS NOT NULL)
      OR (outcome IN ('unchanged','published') AND next_attempt_at IS NULL))
);
ALTER TABLE dane_city_refresh_attempt
  ADD COLUMN IF NOT EXISTS fetched_document_id text REFERENCES source_document(id);
ALTER TABLE dane_city_refresh_attempt
  ADD COLUMN IF NOT EXISTS response_status integer,
  ADD COLUMN IF NOT EXISTS response_content_type text,
  ADD COLUMN IF NOT EXISTS response_url text,
  ADD COLUMN IF NOT EXISTS body_classification text;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conrelid='dane_city_refresh_attempt'::regclass
                   AND conname='dane_city_refresh_attempt_fetched_document_sha_check') THEN
    ALTER TABLE dane_city_refresh_attempt
      ADD CONSTRAINT dane_city_refresh_attempt_fetched_document_sha_check
      CHECK (fetched_document_id IS NULL OR fetched_sha256=fetched_document_id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS dane_city_refresh_attempt_latest
  ON dane_city_refresh_attempt(request_id,attempt_no DESC);

-- A downloaded original is committed and linked before parsing/publication.
-- Invalid later cohorts therefore keep their bytes and exact source identity.
CREATE TABLE IF NOT EXISTS dane_city_refresh_source (
  request_id bigint NOT NULL REFERENCES dane_city_refresh_request(request_id),
  observed_on date NOT NULL,
  document_id text NOT NULL REFERENCES source_document(id),
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
  retained_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(request_id,document_id),
  UNIQUE(request_id,source_sha256),
  CHECK (document_id=source_sha256)
);
CREATE INDEX IF NOT EXISTS dane_city_refresh_source_document ON dane_city_refresh_source(document_id);

-- Exact non-ZIP HTTP responses are retained as audit evidence, never as a
-- source_document claiming to be an application/zip original.
CREATE TABLE IF NOT EXISTS dane_city_refresh_response_audit (
  request_id bigint NOT NULL REFERENCES dane_city_refresh_request(request_id),
  attempt_no integer NOT NULL CHECK (attempt_no>0),
  response_sha256 text NOT NULL CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
  response_bytes bytea NOT NULL,
  response_status integer NOT NULL,
  response_content_type text,
  response_url text NOT NULL,
  body_classification text NOT NULL CHECK (body_classification IN
      ('html','truncated_zip','other_non_zip','off_domain_redirect','redirect_target_mismatch',
       'wrong_day_zip','unverifiable_member_date','invalid_zip_members')),
  captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(request_id,attempt_no),
  CHECK (octet_length(response_bytes)>0)
);

DO $$
DECLARE tab text;
BEGIN
  FOREACH tab IN ARRAY ARRAY['dane_city_page_snapshot','dane_city_page_row',
                              'dane_city_refresh_request','dane_city_refresh_attempt',
                              'dane_city_refresh_source','dane_city_refresh_response_audit'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS immutable_private_history ON %I',tab);
    EXECUTE format('DROP TRIGGER IF EXISTS retain_private_history ON %I',tab);
    EXECUTE format('CREATE TRIGGER immutable_private_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
    EXECUTE format('CREATE TRIGGER retain_private_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
  END LOOP;
END $$;
GRANT SELECT ON dane_city_page_snapshot,dane_city_page_row,dane_city_refresh_request,dane_city_refresh_attempt,dane_city_refresh_source TO agro_reader;
GRANT SELECT,INSERT ON dane_city_page_snapshot,dane_city_page_row,dane_city_refresh_request,dane_city_refresh_attempt,dane_city_refresh_source,dane_city_refresh_response_audit TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE dane_city_page_snapshot_snapshot_id_seq,
  dane_city_refresh_request_request_id_seq TO agro_ingestor;


-- Accepted publication heads are separate from the mutable ingestion_asset
-- last-attempt pointer. Historical source/member/price rows remain append-only.
-- Final three-reason request checks are installed once in the O4 request schema above.

CREATE TABLE IF NOT EXISTS dane_city_revision_source (
  source_url text NOT NULL,
  observed_on date NOT NULL,
  archive_id text NOT NULL REFERENCES source_document(id),
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
  registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(source_url,observed_on,archive_id),
  UNIQUE(archive_id),
  CHECK (archive_id=source_sha256)
);

CREATE TABLE IF NOT EXISTS dane_city_cohort_acceptance (
  acceptance_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_url text NOT NULL,
  observed_on date NOT NULL,
  archive_id text NOT NULL,
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
  processor_version text NOT NULL,
  member_count integer NOT NULL CHECK (member_count>0),
  price_count integer NOT NULL CHECK (price_count>0),
  classification_count integer NOT NULL CHECK (classification_count>0),
  cohort_sha256 text NOT NULL CHECK (cohort_sha256 ~ '^[a-f0-9]{64}$'),
  accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY(source_url,observed_on,archive_id)
    REFERENCES dane_city_revision_source(source_url,observed_on,archive_id),
  CHECK (archive_id=source_sha256),
  CHECK (price_count=classification_count),
  UNIQUE(acceptance_id,source_url,observed_on,archive_id)
);
CREATE INDEX IF NOT EXISTS dane_city_cohort_acceptance_source_latest
  ON dane_city_cohort_acceptance(source_url,observed_on,acceptance_id DESC);

CREATE TABLE IF NOT EXISTS dane_city_cohort_current (
  source_url text NOT NULL,
  observed_on date NOT NULL,
  acceptance_id bigint NOT NULL REFERENCES dane_city_cohort_acceptance(acceptance_id),
  archive_id text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(source_url,observed_on),
  FOREIGN KEY(acceptance_id,source_url,observed_on,archive_id)
    REFERENCES dane_city_cohort_acceptance(acceptance_id,source_url,observed_on,archive_id)
);
-- Query-time membership is a child-document lookup followed by this small
-- current-head index; it does not enumerate all price rows or all ZIPs.
CREATE INDEX IF NOT EXISTS dane_city_cohort_current_archive
  ON dane_city_cohort_current(archive_id,source_url,observed_on);
CREATE INDEX IF NOT EXISTS source_archive_member_document_archive
  ON source_archive_member(document_id,archive_id);

DO $$ DECLARE tab text; BEGIN
  FOREACH tab IN ARRAY ARRAY['dane_city_revision_source','dane_city_cohort_acceptance'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS immutable_private_history ON %I',tab);
    EXECUTE format('DROP TRIGGER IF EXISTS retain_private_history ON %I',tab);
    EXECUTE format('CREATE TRIGGER immutable_private_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
    EXECUTE format('CREATE TRIGGER retain_private_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
  END LOOP;
END $$;
GRANT SELECT ON dane_city_revision_source,dane_city_cohort_acceptance,dane_city_cohort_current
  TO agro_reader,agro_ingestor;
GRANT INSERT ON dane_city_revision_source,dane_city_cohort_acceptance
  TO agro_ingestor;
GRANT INSERT,UPDATE ON dane_city_cohort_current TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE dane_city_cohort_acceptance_acceptance_id_seq
  TO agro_ingestor;


-- Keep all 18 columns, order and types of the accepted public price view.
-- Enrolled refresh candidates are visible only when their parent archive is
-- the accepted source/day head. Unregistered legacy membership remains visible,
-- including a child shared by a staged candidate and a legacy archive.
CREATE OR REPLACE VIEW published_regional_price AS
 SELECT r.document_id,r.source_locator,r.observed_on,r.product_id,r.product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  coalesce(o.corrected_min_price,r.min_price) AS min_price,
  coalesce(o.corrected_max_price,r.max_price) AS max_price,r.unit,
  coalesce(o.corrected_min_unit_price,r.min_unit_price) AS min_unit_price,
  coalesce(o.corrected_max_unit_price,r.max_unit_price) AS max_unit_price,r.source_page
 FROM regional_price r LEFT JOIN verified_city_pdf_price_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator
 WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict c
   WHERE c.document_id=r.document_id OFFSET 0)
 AND (
   NOT EXISTS (
     SELECT 1 FROM source_archive_member enrolled_member
     JOIN dane_city_revision_source enrolled_source
       ON enrolled_source.archive_id=enrolled_member.archive_id
     WHERE enrolled_member.document_id=r.document_id
   )
   OR EXISTS (
     SELECT 1 FROM source_archive_member active_member
     JOIN dane_city_cohort_current active_head
       ON active_head.archive_id=active_member.archive_id
     WHERE active_member.document_id=r.document_id
   )
   OR EXISTS (
     SELECT 1 FROM ingestion_asset direct_asset
     WHERE direct_asset.document_id=r.document_id
       AND direct_asset.kind='city-pdf'
   )
   OR EXISTS (
     SELECT 1 FROM source_archive_member legacy_member
     WHERE legacy_member.document_id=r.document_id
       AND NOT EXISTS (
         SELECT 1 FROM dane_city_revision_source enrolled_legacy_parent
         WHERE enrolled_legacy_parent.archive_id=legacy_member.archive_id
       )
   )
 );
GRANT SELECT ON published_regional_price TO agro_reader,agro_ingestor;


-- Fair bounded polling across retained prior-year page URLs.
-- Private only: append-only poll outcomes let exact page rotation move past failures.
CREATE TABLE IF NOT EXISTS dane_city_page_poll_attempt (
  poll_attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  page_url text NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('observed','failed')),
  attempted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  error text
);
CREATE INDEX IF NOT EXISTS dane_city_page_poll_attempt_latest
  ON dane_city_page_poll_attempt(page_url,attempted_at DESC,poll_attempt_id DESC);
DROP TRIGGER IF EXISTS immutable_private_history ON dane_city_page_poll_attempt;
DROP TRIGGER IF EXISTS retain_private_history ON dane_city_page_poll_attempt;
CREATE TRIGGER immutable_private_history BEFORE UPDATE ON dane_city_page_poll_attempt
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
CREATE TRIGGER retain_private_history BEFORE DELETE OR TRUNCATE ON dane_city_page_poll_attempt
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON dane_city_page_poll_attempt TO agro_reader,agro_ingestor;
GRANT INSERT ON dane_city_page_poll_attempt TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE dane_city_page_poll_attempt_poll_attempt_id_seq TO agro_ingestor;
