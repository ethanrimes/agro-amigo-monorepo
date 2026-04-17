-- Migration: Small RPCs returning distinct market_ids that carry data for a
-- product, for the map overlay's "which markets to highlight" layer.
-- Replaces a client-side `select('market_id').limit(5000)` + Set-dedup that
-- pulled 5000 rows of waste and was the most likely cause of the map's
-- intermittent 57014 timeouts on cold connections.
-- Date: 2026-04-16

CREATE OR REPLACE FUNCTION get_price_markets_for_product(
  p_product_id UUID,
  p_days INT,
  p_presentation_id UUID DEFAULT NULL,
  p_units_id UUID DEFAULT NULL
) RETURNS SETOF UUID
LANGUAGE sql STABLE AS $$
  SELECT DISTINCT market_id
  FROM price_observations
  WHERE product_id = p_product_id
    AND market_id IS NOT NULL
    AND price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_presentation_id IS NULL OR presentation_id = p_presentation_id)
    AND (p_units_id IS NULL OR units_id = p_units_id);
$$;

CREATE OR REPLACE FUNCTION get_supply_markets_for_product(
  p_product_id UUID,
  p_days INT
) RETURNS SETOF UUID
LANGUAGE sql STABLE AS $$
  SELECT DISTINCT market_id
  FROM supply_observations
  WHERE product_id = p_product_id
    AND market_id IS NOT NULL
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END;
$$;

COMMENT ON FUNCTION get_price_markets_for_product IS 'Distinct price-market IDs for a product in a time window (map overlay).';
COMMENT ON FUNCTION get_supply_markets_for_product IS 'Distinct supply-market IDs for a product in a time window (map overlay).';
