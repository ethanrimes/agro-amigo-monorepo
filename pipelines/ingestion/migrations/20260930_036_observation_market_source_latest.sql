-- Run outside a transaction. Market/series availability needs one eligible
-- published observation per exact source family, not a scan of all history.
CREATE INDEX CONCURRENTLY IF NOT EXISTS observation_market_source_latest
  ON price_observation(market_id, source_id, observed_on DESC)
  INCLUDE (product_id, document_id, source_locator, period, unit);
