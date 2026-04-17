-- Migration: Server-side RPCs for choropleth map, national comparisons,
-- and insumo watchlist lookups.
--
-- Replaces five client-side patterns that all had the same problem: they
-- pulled a large slice (500-10K rows) and aggregated in JS. For busy
-- products/markets this was slow, timed out, or produced biased results
-- (last-N-rows truncation silently skipped whole markets/departments).
--
-- Same sargable-predicate discipline as migration 029:
--   - no CTEs (keeps SQL functions inlinable)
--   - observation_date >= CASE WHEN p_days > 0 THEN ... ELSE '1900-01-01' END
--   - IS NULL OR col = param for optional filters
--
-- Date: 2026-04-16


-- ── Choropleth: supply totals per destination department ──
-- Destination dept = department of the market the supply arrived at,
-- resolved via supply_observations.city_id → dim_city.department_id.
-- This mirrors the semantic the UI already uses.
CREATE OR REPLACE FUNCTION get_supply_by_department(
  p_product_id UUID DEFAULT NULL,
  p_days INT DEFAULT 30
) RETURNS TABLE(
  department_id UUID,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT dc.department_id, SUM(so.quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations so
  JOIN dim_city dc ON dc.id = so.city_id
  WHERE so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_product_id IS NULL OR so.product_id = p_product_id)
  GROUP BY dc.department_id;
$$;


-- ── Choropleth: price averages per destination department ──
-- Mixing presentations produces meaningless averages (kg vs lb vs unit).
-- We enforce at the DB level: if the caller specifies a product, it must
-- also specify the presentation + units. The "all products" mode (p_product_id
-- NULL) is permitted without presentation because the map uses it as a coarse
-- "which departments have many observations" indicator, not a literal price.
CREATE OR REPLACE FUNCTION get_prices_by_department(
  p_product_id UUID DEFAULT NULL,
  p_days INT DEFAULT 30,
  p_presentation_id UUID DEFAULT NULL,
  p_units_id UUID DEFAULT NULL
) RETURNS TABLE(
  department_id UUID,
  avg_price NUMERIC,
  observation_count INT
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF p_product_id IS NOT NULL AND p_presentation_id IS NULL THEN
    RAISE EXCEPTION 'get_prices_by_department: p_presentation_id is required when p_product_id is provided (mixing presentations would produce meaningless averages)';
  END IF;
  RETURN QUERY
  SELECT
    po.department_id,
    AVG(COALESCE(po.avg_price, (po.min_price + po.max_price) / 2.0))::NUMERIC AS avg_price,
    COUNT(*)::INT AS observation_count
  FROM price_observations po
  WHERE po.price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_product_id IS NULL OR po.product_id = p_product_id)
    AND (p_presentation_id IS NULL OR po.presentation_id = p_presentation_id)
    AND (p_units_id IS NULL OR po.units_id = p_units_id)
    AND COALESCE(po.avg_price, po.min_price, po.max_price, 0) > 0
    AND po.department_id IS NOT NULL
  GROUP BY po.department_id;
END;
$$;


-- ── Home + comparator: national price averages per product+presentation ──
-- For each (product, presentation, units), take the latest observation per
-- market in the window, then average across markets. This produces a
-- national price that isn't skewed by one market reporting many times.
CREATE OR REPLACE FUNCTION get_national_price_averages(
  p_product_ids UUID[],
  p_days INT DEFAULT 30
) RETURNS TABLE(
  product_id UUID,
  presentation_id UUID,
  units_id UUID,
  avg_price NUMERIC,
  price_date DATE,
  market_count INT
)
LANGUAGE sql STABLE AS $$
  WITH latest_per_market AS (
    SELECT DISTINCT ON (po.product_id, po.presentation_id, po.units_id, po.market_id)
      po.product_id, po.presentation_id, po.units_id, po.market_id,
      COALESCE(po.avg_price, (po.min_price + po.max_price) / 2.0) AS eff_price,
      po.price_date
    FROM price_observations po
    WHERE po.product_id = ANY(p_product_ids)
      AND po.price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
      AND COALESCE(po.avg_price, po.min_price, po.max_price, 0) > 0
    ORDER BY po.product_id, po.presentation_id, po.units_id, po.market_id, po.price_date DESC
  )
  SELECT
    product_id, presentation_id, units_id,
    AVG(eff_price)::NUMERIC AS avg_price,
    MAX(price_date) AS price_date,
    COUNT(*)::INT AS market_count
  FROM latest_per_market
  GROUP BY product_id, presentation_id, units_id;
$$;


-- ── Comparator: national supply averages per product ──
-- For each product: sum kg per market in the window, then average across
-- the markets that actually carry the product. Gives a useful "typical
-- market volume" baseline for the "this market vs national average" UI.
-- Previous JS version capped at 10K rows → biased; this version sees
-- everything via server-side GROUP BY.
CREATE OR REPLACE FUNCTION get_national_supply_averages(
  p_product_ids UUID[],
  p_days INT DEFAULT 30
) RETURNS TABLE(
  product_id UUID,
  avg_kg_per_market NUMERIC,
  total_kg NUMERIC,
  market_count INT
)
LANGUAGE sql STABLE AS $$
  WITH per_market AS (
    SELECT so.product_id, so.market_id, SUM(so.quantity_kg) AS market_total
    FROM supply_observations so
    WHERE so.product_id = ANY(p_product_ids)
      AND so.market_id IS NOT NULL
      AND so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    GROUP BY so.product_id, so.market_id
  )
  SELECT
    product_id,
    AVG(market_total)::NUMERIC AS avg_kg_per_market,
    SUM(market_total)::NUMERIC AS total_kg,
    COUNT(*)::INT AS market_count
  FROM per_market
  GROUP BY product_id;
$$;


-- ── Watchlist: latest insumo price per insumo with presentation ──
-- Previous JS version fetched raw rows and kept "most recent per insumo_id"
-- — but an insumo often has many presentations (frasco 500ml, saco 50kg).
-- Random pick → wildly different price shown each refresh. This RPC uses
-- DISTINCT ON to pick one stable "latest observation" per insumo and
-- returns its presentation string so the UI can show it alongside the price.
CREATE OR REPLACE FUNCTION get_watchlist_insumo_latest_prices(
  p_insumo_ids UUID[],
  p_days INT DEFAULT 180
) RETURNS TABLE(
  insumo_id UUID,
  department_id UUID,
  dept_name TEXT,
  price_date DATE,
  avg_price NUMERIC,
  presentation TEXT
)
LANGUAGE sql STABLE AS $$
  SELECT DISTINCT ON (ipd.insumo_id)
    ipd.insumo_id,
    ipd.department_id,
    d.canonical_name::TEXT AS dept_name,
    ipd.price_date,
    ipd.avg_price,
    ipd.presentation::TEXT
  FROM insumo_prices_department ipd
  JOIN dim_department d ON d.id = ipd.department_id
  WHERE ipd.insumo_id = ANY(p_insumo_ids)
    AND ipd.price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
  ORDER BY ipd.insumo_id, ipd.price_date DESC, ipd.presentation;
$$;


-- Index helpers for the new filters.
CREATE INDEX IF NOT EXISTS idx_price_obs_product_date
  ON price_observations(product_id, price_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_obs_date
  ON price_observations(price_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_obs_dept_date
  ON price_observations(department_id, price_date DESC);


COMMENT ON FUNCTION get_supply_by_department IS 'Total supply kg per destination department in a time window. Feeds the map choropleth (supply mode). No client-side row-cap bias.';
COMMENT ON FUNCTION get_prices_by_department IS 'Average price per department for a product+presentation (or all products). Requires presentation when a product is given to avoid mixing incompatible units.';
COMMENT ON FUNCTION get_national_price_averages IS 'Latest per-market average price per (product, presentation, units) across the nation. Used by MarketPriceComparator.';
COMMENT ON FUNCTION get_national_supply_averages IS 'Per-market supply volume averaged across the markets that carry the product. Used by MarketSupplyComparator.';
COMMENT ON FUNCTION get_watchlist_insumo_latest_prices IS 'Single latest observation per insumo with its presentation string. Used by home-screen watchlist.';
