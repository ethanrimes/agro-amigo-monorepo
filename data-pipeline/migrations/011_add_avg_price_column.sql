-- Migration: Add avg_price column for milk and other products with average prices
-- Date: 2026-04-10

ALTER TABLE processed_prices ADD COLUMN IF NOT EXISTS avg_price DECIMAL(12, 2);
ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS avg_price DECIMAL(12, 2);

COMMENT ON COLUMN processed_prices.avg_price IS 'Average/mean price (used for milk and products with mid-point pricing)';
COMMENT ON COLUMN price_observations.avg_price IS 'Average/mean price (used for milk and products with mid-point pricing)';
