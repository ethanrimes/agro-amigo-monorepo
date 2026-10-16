-- Run outside a transaction. Catalog identities and each latest eligible
-- summary can use the same narrow index without reading old JSON payloads.
CREATE INDEX CONCURRENTLY IF NOT EXISTS historical_monthly_summary_catalog_seek
 ON historical_price(product_name,market_name,unit,observed_on DESC)
 WHERE series='dane-monthly-summary';
