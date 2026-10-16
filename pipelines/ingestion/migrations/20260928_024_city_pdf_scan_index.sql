-- Run outside a transaction. Let the hourly correction scanner seek archived
-- city PDFs by immutable document ID without sorting or scanning every source.
CREATE INDEX CONCURRENTLY IF NOT EXISTS source_document_city_pdf_scan
 ON source_document(id)
 WHERE metadata->>'ingestion_kind'='city-pdf';
