-- Run outside a transaction. The market directory must count every eligible
-- recent product/market identity while checking review provenance. Cover those
-- checks from the date-range index instead of fetching each observation heap row.
CREATE INDEX CONCURRENTLY IF NOT EXISTS observation_directory_cover
  ON price_observation(observed_on DESC)
  INCLUDE (product_id, market_id, source_id, document_id, source_locator, period, unit);
