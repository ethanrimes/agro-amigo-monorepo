-- Apply outside a transaction. Cover exact-source revision keys so catalog
-- repair priority can keep its newest/strictly-older checks and four-second
-- budget without fetching the wide immutable quote payload. Existing indexes,
-- source rows and ordinary catalog FIFO ordering are retained.
CREATE INDEX CONCURRENTLY IF NOT EXISTS official_quote_repair_priority_cover
  ON public.official_price_quote(document_id,source_locator,parsed_at)
  INCLUDE(quote_key,parser_version);
