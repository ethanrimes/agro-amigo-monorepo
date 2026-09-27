-- Lookup archived versions by the real publisher URL without loading bytea.
CREATE INDEX IF NOT EXISTS source_document_url_retrieved
ON source_document(source_url,retrieved_at DESC);
