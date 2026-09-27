-- A completed native re-extraction replaces publication eligibility, never raw
-- evidence. Seed the previously deployed v4 guard only where committed v4 rows
-- prove that extraction/publication completed in the original transaction.
-- This table has been standard since 20260926_automation; repeat its definition
-- so this additive migration is also safe on installations without that file.
CREATE TABLE IF NOT EXISTS ingestion_checkpoint (
 document_id text NOT NULL REFERENCES source_document(id),processor_version text NOT NULL,
 step text NOT NULL,records bigint NOT NULL DEFAULT 0,completed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,processor_version,step)
);

INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
SELECT DISTINCT a.document_id,'inputs-pdf-v4','inputs-pdf:published',0
FROM ingestion_asset a WHERE a.kind='inputs-pdf' AND a.document_id IS NOT NULL
AND EXISTS(SELECT 1 FROM historical_price h WHERE h.document_id=a.document_id
  AND h.series IN ('dane-inputs-pdf','dane-inputs-pdf-unresolved')
  AND h.details->>'parser_version'='inputs-pdf-v4')
ON CONFLICT DO NOTHING;

CREATE OR REPLACE VIEW published_input_price AS
SELECT p.* FROM input_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
);
CREATE OR REPLACE VIEW published_input_municipal_price AS
SELECT p.* FROM input_municipal_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
);
GRANT SELECT ON published_input_price,published_input_municipal_price TO agro_reader;
GRANT SELECT,INSERT ON ingestion_checkpoint TO agro_ingestor;
GRANT SELECT ON ingestion_checkpoint TO agro_reader;
