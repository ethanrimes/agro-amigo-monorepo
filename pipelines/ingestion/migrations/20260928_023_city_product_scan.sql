-- Immutable, versioned evidence that an archived city PDF was checked for
-- native product-column spacing. Retry rows are nonterminal and cool down.
CREATE TABLE IF NOT EXISTS city_product_scan (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 scan_version text NOT NULL,
 status text NOT NULL CHECK(status IN ('complete','review','retry')),
 source_sha256 text NOT NULL CHECK(source_sha256=document_id),
 source_url text NOT NULL,
 storage text,
 candidate_rows integer NOT NULL DEFAULT 0 CHECK(candidate_rows>=0),
 inserted_rows integer NOT NULL DEFAULT 0 CHECK(inserted_rows>=0),
 reason_code text,
 scanned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(inserted_rows<=candidate_rows),
 CHECK((status='complete' AND reason_code IS NULL) OR
       (status<>'complete' AND reason_code IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS city_product_scan_terminal
 ON city_product_scan(document_id,scan_version)
 WHERE status IN ('complete','review');
CREATE INDEX IF NOT EXISTS city_product_scan_retry_recent
 ON city_product_scan(document_id,scan_version,scanned_at DESC)
 WHERE status='retry';
DROP TRIGGER IF EXISTS immutable_history ON city_product_scan;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_product_scan
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_product_scan;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_product_scan
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_product_scan TO agro_reader;
GRANT SELECT,INSERT ON city_product_scan TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE city_product_scan_id_seq TO agro_ingestor;
