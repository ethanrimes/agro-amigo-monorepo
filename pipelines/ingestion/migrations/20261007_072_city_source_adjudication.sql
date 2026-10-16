-- Append-only attribution for exact-source city member adjudication.
-- Eligibility is separately SHA-bound in a reviewed source registry.
CREATE TABLE IF NOT EXISTS city_source_adjudication (
  document_id text NOT NULL REFERENCES source_document(id),
  policy_version text NOT NULL,
  archive_id text NOT NULL REFERENCES source_document(id),
  entry_name text NOT NULL,
  evidence_document_id text NOT NULL REFERENCES source_document(id),
  source_grid_sha256 text NOT NULL CHECK (source_grid_sha256 ~ '^[a-f0-9]{64}$'),
  full17_sha256 text NOT NULL CHECK (full17_sha256 ~ '^[a-f0-9]{64}$'),
  provider_result_hashes jsonb NOT NULL,
  prior_tasks jsonb NOT NULL,
  records integer NOT NULL CHECK(records > 0),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (document_id, policy_version),
  FOREIGN KEY (archive_id,entry_name) REFERENCES source_archive_member(archive_id,entry_name),
  CHECK (jsonb_typeof(provider_result_hashes) = 'object'),
  CHECK (jsonb_typeof(prior_tasks) = 'array')
);
DROP TRIGGER IF EXISTS immutable_history ON city_source_adjudication;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_source_adjudication
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_source_adjudication;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_source_adjudication
  FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_source_adjudication TO agro_reader;
GRANT SELECT,INSERT ON city_source_adjudication TO agro_ingestor;
