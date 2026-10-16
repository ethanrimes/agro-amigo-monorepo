-- Run outside a transaction. Preserve the exact package and original unit
-- dimensions while seeking the newest dated city quote within each identity.
CREATE INDEX CONCURRENTLY IF NOT EXISTS regional_quote_latest_identity
  ON regional_price(product_id, market_name, lower(btrim(presentation)), quantity,
    lower(btrim(source_unit)), unit, observed_on DESC, round DESC);
