-- Additive, durable phase checkpoints. Existing sources and prices stay intact.
CREATE TABLE IF NOT EXISTS ingestion_checkpoint (
 document_id text NOT NULL REFERENCES source_document(id),
 processor_version text NOT NULL,
 step text NOT NULL,
 records bigint NOT NULL DEFAULT 0,
 completed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,processor_version,step)
);
GRANT SELECT,INSERT ON ingestion_checkpoint TO agro_ingestor;
GRANT SELECT ON ingestion_checkpoint TO agro_reader;

CREATE INDEX IF NOT EXISTS historical_price_document_date ON historical_price(document_id,observed_on);
