-- Existing production databases can build the same index CONCURRENTLY during
-- maintenance. This idempotent definition also supports fresh installations.
CREATE INDEX IF NOT EXISTS regional_market_latest
    ON regional_price(market_name, observed_on DESC);
