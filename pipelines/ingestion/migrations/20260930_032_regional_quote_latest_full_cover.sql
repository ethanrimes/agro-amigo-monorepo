-- Run outside a transaction. Include the raw text columns required to
-- evaluate the normalized expression keys during an index-only scan.
CREATE INDEX CONCURRENTLY IF NOT EXISTS regional_quote_latest_full_cover
  ON regional_price(product_id, market_name, lower(btrim(presentation)), quantity,
    lower(btrim(source_unit)), unit, observed_on DESC, round DESC)
  INCLUDE (presentation, source_unit, document_id, source_locator);
