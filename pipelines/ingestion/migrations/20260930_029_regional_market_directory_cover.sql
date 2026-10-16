-- Run outside a transaction. The market directory scans recent city identities;
-- cover the fields needed before its provenance and correction joins so the
-- date range can use index-only reads when visibility permits.
CREATE INDEX CONCURRENTLY IF NOT EXISTS regional_market_directory_cover
  ON regional_price(observed_on DESC)
  INCLUDE (market_name, product_id, document_id, source_locator);
