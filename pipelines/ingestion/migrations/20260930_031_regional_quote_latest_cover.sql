-- Run outside a transaction. Keep quote identities, dates, and provenance in
-- one ordered index so latest-key selection can avoid historical heap reads.
CREATE INDEX CONCURRENTLY IF NOT EXISTS regional_quote_latest_cover
  ON regional_price(product_id, market_name, lower(btrim(presentation)), quantity,
    lower(btrim(source_unit)), unit, observed_on DESC, round DESC)
  INCLUDE (document_id, source_locator);
