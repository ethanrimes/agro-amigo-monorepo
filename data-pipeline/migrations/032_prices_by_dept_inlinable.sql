-- Migration: Map-screen performance fixes for busy products (e.g. "fresa").
--
-- Root cause, supply mode:
--   get_supply_by_department is LANGUAGE sql (so it inlines), but its body
--   carries (p_product_id IS NULL OR so.product_id = p_product_id). Once
--   PostgREST's prepared statement switches to a generic plan, the OR
--   branch makes the planner hedge and it stops using
--   idx_supply_obs_product_date — instead scanning 30 days of
--   supply_observations (millions of rows, dominated by Corabastos) and
--   joining dim_city row-by-row. Result: 57014 statement timeout on
--   popular products.
--
-- Root cause, price mode:
--   get_prices_by_department is LANGUAGE plpgsql, so it isn't inlined at
--   all and has the same generic-plan problem plus an extra opaque layer.
--
-- Presentations chip row:
--   The client also fetched up to 1000 raw price_observations rows with
--   two embedded joins just to dedupe a handful of (presentation, units)
--   tuples — wasted payload and planner time for popular products.
--
-- Fixes here:
--   1. Convert get_prices_by_department to LANGUAGE sql. Its only reason
--      to be plpgsql was a RAISE EXCEPTION guard for "product without
--      presentation mixes units" — that check is enforced client-side
--      already (agroamigo-app/src/api/map.ts::getPricesByDepartment).
--
--   2. Add product-required variants: get_prices_by_department_for_product
--      and get_supply_by_department_for_product. No nullable OR, so the
--      planner always uses the (product_id, date) composite index. The
--      map client now calls these — the null-product path is already
--      skipped client-side because a cross-product aggregate is meaningless.
--
--   3. Add get_product_presentations_for_map: server-side DISTINCT over
--      (presentation_id, units_id) joined to dim names, so the client
--      receives a handful of rows instead of up to 1000.
--
-- Date: 2026-04-16


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
LANGUAGE sql STABLE AS $$
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
$$;


CREATE OR REPLACE FUNCTION get_prices_by_department_for_product(
  p_product_id UUID,
  p_presentation_id UUID,
  p_units_id UUID,
  p_days INT DEFAULT 30
) RETURNS TABLE(
  department_id UUID,
  avg_price NUMERIC,
  observation_count INT
)
LANGUAGE sql STABLE AS $$
  SELECT
    po.department_id,
    AVG(COALESCE(po.avg_price, (po.min_price + po.max_price) / 2.0))::NUMERIC AS avg_price,
    COUNT(*)::INT AS observation_count
  FROM price_observations po
  WHERE po.product_id = p_product_id
    AND po.presentation_id = p_presentation_id
    AND po.units_id = p_units_id
    AND po.price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND COALESCE(po.avg_price, po.min_price, po.max_price, 0) > 0
    AND po.department_id IS NOT NULL
  GROUP BY po.department_id;
$$;


CREATE OR REPLACE FUNCTION get_supply_by_department_for_product(
  p_product_id UUID,
  p_days INT DEFAULT 30
) RETURNS TABLE(
  department_id UUID,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT dc.department_id, SUM(so.quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations so
  JOIN dim_city dc ON dc.id = so.city_id
  WHERE so.product_id = p_product_id
    AND so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
  GROUP BY dc.department_id;
$$;


CREATE OR REPLACE FUNCTION get_product_presentations_for_map(
  p_product_id UUID,
  p_days INT DEFAULT 30
) RETURNS TABLE(
  presentation_id UUID,
  units_id UUID,
  presentation_name TEXT,
  units_name TEXT
)
LANGUAGE sql STABLE AS $$
  SELECT DISTINCT
    po.presentation_id,
    po.units_id,
    dp.canonical_name::TEXT AS presentation_name,
    du.canonical_name::TEXT AS units_name
  FROM price_observations po
  LEFT JOIN dim_presentation dp ON dp.id = po.presentation_id
  LEFT JOIN dim_units du ON du.id = po.units_id
  WHERE po.product_id = p_product_id
    AND po.price_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND po.presentation_id IS NOT NULL
    AND po.units_id IS NOT NULL;
$$;


COMMENT ON FUNCTION get_prices_by_department IS 'Average price per department (optionally filtered). LANGUAGE sql so it inlines. Kept for backward compat; the map uses the _for_product variant.';
COMMENT ON FUNCTION get_prices_by_department_for_product IS 'Average price per department for a specific product+presentation+units. Product-required, no nullable OR, so the planner always picks idx_price_obs_product_date.';
COMMENT ON FUNCTION get_supply_by_department_for_product IS 'Total supply kg per destination department for a specific product. Product-required, no nullable OR, so the planner always picks idx_supply_obs_product_date.';
COMMENT ON FUNCTION get_product_presentations_for_map IS 'Distinct (presentation, units) tuples for a product in a time window with display names. Replaces a client-side dedupe over 1000 raw rows.';
