-- Run outside a transaction. Narrow retained revision keys cover source-viewer
-- selection; only the final <=100 rows fetch price/name/basis payloads.
CREATE INDEX CONCURRENTLY IF NOT EXISTS official_quote_document_revisions
 ON official_price_quote(document_id,source_locator,parsed_at DESC)
 INCLUDE(observed_on,parser_version);
