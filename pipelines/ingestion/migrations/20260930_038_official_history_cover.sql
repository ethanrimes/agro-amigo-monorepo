-- History candidates need only identity/revision fields. Original JSON payloads
-- are fetched after choosing winners, keeping concurrent reads off the heap.
CREATE INDEX CONCURRENTLY IF NOT EXISTS official_quote_history_cover
 ON official_price_quote(quote_key,observed_on DESC)
 INCLUDE(document_id,source_locator,parser_version,parsed_at,series);
