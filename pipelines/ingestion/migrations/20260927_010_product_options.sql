-- Product filter choices need all historical market/unit identities but not
-- wide observation payloads. Build the same index CONCURRENTLY on a live DB.
CREATE INDEX IF NOT EXISTS observation_product_options
 ON price_observation(product_id,observed_on DESC)
 INCLUDE(market_id,source_id,unit,document_id);
