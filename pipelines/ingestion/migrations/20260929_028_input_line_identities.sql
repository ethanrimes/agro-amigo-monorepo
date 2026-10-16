-- Preserve legacy links and all evidence while splitting verified commercial lines.
-- Re-extraction under input-lines-v1 fills aliases and publishes new identities;
-- a legacy observation is hidden only after its exact replacement exists.
CREATE TABLE IF NOT EXISTS input_identity_alias (
 legacy_id text NOT NULL,id text NOT NULL,PRIMARY KEY(legacy_id,id),CHECK(legacy_id<>id)
);
DROP TRIGGER IF EXISTS retain_history ON input_identity_alias;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON input_identity_alias
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON input_identity_alias;
CREATE TRIGGER immutable_history BEFORE UPDATE ON input_identity_alias
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON input_identity_alias TO agro_ingestor;
GRANT SELECT ON input_identity_alias TO agro_reader;

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
);
CREATE OR REPLACE VIEW published_input_municipal_price AS
SELECT p.* FROM input_municipal_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
) AND NOT EXISTS (
 SELECT 1 FROM input_identity_alias a JOIN input_municipal_price replacement ON replacement.id=a.id
 WHERE a.legacy_id=p.id AND replacement.department=p.department
 AND replacement.municipality=p.municipality AND replacement.observed_on=p.observed_on
 AND (replacement.name,replacement.presentation,replacement.brand,replacement.registration,replacement.product_line)
   IS NOT DISTINCT FROM (p.name,p.presentation,p.brand,p.registration,p.product_line)
 AND (SELECT retrieved_at FROM source_document WHERE id=replacement.document_id)
   >= (SELECT retrieved_at FROM source_document WHERE id=p.document_id)
);
GRANT SELECT ON published_input_price,published_input_municipal_price TO agro_reader;
