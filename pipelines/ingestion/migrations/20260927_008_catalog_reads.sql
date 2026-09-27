-- Production can build these same indexes CONCURRENTLY. Catalog reads need
-- narrow covering values, not the source/history payload heap for every row.
CREATE INDEX IF NOT EXISTS observation_catalog_window
 ON price_observation(observed_on DESC,source_id)
 INCLUDE(product_id,market_id,unit,price,document_id);
-- Supports loose distinct literal-name seeks and the latest mapped price date.
CREATE INDEX IF NOT EXISTS regional_catalog_names
 ON regional_price(product_id,product_name,observed_on DESC)
 INCLUDE(market_name);
-- Exact product/date quote lookup after literal-name date selection.
CREATE INDEX IF NOT EXISTS regional_product_latest
 ON regional_price(product_id,observed_on DESC);
