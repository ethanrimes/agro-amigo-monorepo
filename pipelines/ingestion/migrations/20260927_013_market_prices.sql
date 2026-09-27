-- May be built CONCURRENTLY in production. Exact-market pages should not scan
-- the complete observation window or every other market's quote payloads.
CREATE INDEX IF NOT EXISTS observation_market_options
 ON price_observation(market_id,observed_on DESC)
 INCLUDE(product_id,source_id,period,unit,document_id);
