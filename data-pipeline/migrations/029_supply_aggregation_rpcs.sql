-- Migration: Server-side aggregation RPCs for supply summaries.
--
-- Previously the mobile + web apps fetched raw supply_observations rows and
-- aggregated client-side (top products, totals, provenance bars). For
-- busy markets like Corabastos (~4.7M rows) that timed out (Postgres 57014)
-- and generated ~1 GB payloads. These RPCs do the aggregation server-side
-- and return only what the UI renders.
--
-- Key planner notes (learned the hard way):
--   1. A LANGUAGE sql function is only inlined when the body is a single
--      SELECT with no CTE and no aggregates-over-CTE. A WITH rows AS (...)
--      block blocks inlining and forces a generic plan that ignores the
--      actual parameter values → seq scan on 20M+ rows → 57014 timeout.
--   2. `(p_days <= 0 OR observation_date >= (CURRENT_DATE - p_days))` is not
--      sargable: the planner can't push it to the composite index. Rewrite
--      as `observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days
--      ELSE DATE '1900-01-01' END` so it becomes a direct range scan.
--   3. `(p_product_id IS NULL OR product_id = p_product_id)` is fine once
--      the function is inlinable — PG constant-folds the NULL check per call.
--
-- Indexes:
--   - (market_id, observation_date DESC) for the market-centric RPCs
--   - (product_id, observation_date DESC) for the product-centric RPCs
--
-- Date: 2026-04-16

CREATE INDEX IF NOT EXISTS idx_supply_obs_market_date
  ON supply_observations(market_id, observation_date DESC);

CREATE INDEX IF NOT EXISTS idx_supply_obs_product_date
  ON supply_observations(product_id, observation_date DESC);


-- Totals for a market in a time window, optionally restricted to one
-- product or one origin department (used by the cross-filter UI).
CREATE OR REPLACE FUNCTION get_market_supply_summary(
  p_market_id UUID,
  p_days INT,
  p_product_id UUID DEFAULT NULL,
  p_prov_dept TEXT DEFAULT NULL
) RETURNS TABLE(
  total_kg NUMERIC,
  daily_avg_kg NUMERIC,
  num_days INT,
  oldest_obs DATE,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(SUM(quantity_kg), 0)::NUMERIC AS total_kg,
    CASE WHEN COUNT(DISTINCT observation_date) > 0
      THEN (SUM(quantity_kg) / COUNT(DISTINCT observation_date))::NUMERIC
      ELSE 0::NUMERIC
    END AS daily_avg_kg,
    COUNT(DISTINCT observation_date)::INT AS num_days,
    MIN(observation_date) AS oldest_obs,
    MAX(observation_date) AS newest_obs
  FROM supply_observations
  WHERE market_id = p_market_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_product_id IS NULL OR product_id = p_product_id)
    AND (p_prov_dept IS NULL OR COALESCE(provenance_dept_name, '') = p_prov_dept);
$$;


-- Top N products at a market (optionally filtered by origin dept).
CREATE OR REPLACE FUNCTION get_market_top_products(
  p_market_id UUID,
  p_days INT,
  p_prov_dept TEXT DEFAULT NULL,
  p_limit INT DEFAULT 10
) RETURNS TABLE(
  product_id UUID,
  product_name TEXT,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT
    so.product_id,
    dp.canonical_name::TEXT AS product_name,
    SUM(so.quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations so
  LEFT JOIN dim_product dp ON dp.id = so.product_id
  WHERE so.market_id = p_market_id
    AND so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_prov_dept IS NULL OR COALESCE(so.provenance_dept_name, '') = p_prov_dept)
  GROUP BY so.product_id, dp.canonical_name
  ORDER BY SUM(so.quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;


-- Top N origin departments for a market (optionally filtered by product).
CREATE OR REPLACE FUNCTION get_market_top_provenance(
  p_market_id UUID,
  p_days INT,
  p_product_id UUID DEFAULT NULL,
  p_limit INT DEFAULT 15
) RETURNS TABLE(
  dept_name TEXT,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')::TEXT AS dept_name,
    SUM(quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations
  WHERE market_id = p_market_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_product_id IS NULL OR product_id = p_product_id)
  GROUP BY COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')
  ORDER BY SUM(quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;


-- ── Product detail page equivalents ──

CREATE OR REPLACE FUNCTION get_product_supply_summary(
  p_product_id UUID,
  p_days INT,
  p_market_id UUID DEFAULT NULL,
  p_prov_dept TEXT DEFAULT NULL
) RETURNS TABLE(
  total_kg NUMERIC,
  daily_avg_kg NUMERIC,
  num_days INT,
  oldest_obs DATE,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(SUM(quantity_kg), 0)::NUMERIC,
    CASE WHEN COUNT(DISTINCT observation_date) > 0
      THEN (SUM(quantity_kg) / COUNT(DISTINCT observation_date))::NUMERIC
      ELSE 0::NUMERIC
    END,
    COUNT(DISTINCT observation_date)::INT,
    MIN(observation_date),
    MAX(observation_date)
  FROM supply_observations
  WHERE product_id = p_product_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_market_id IS NULL OR market_id = p_market_id)
    AND (p_prov_dept IS NULL OR COALESCE(provenance_dept_name, '') = p_prov_dept);
$$;

CREATE OR REPLACE FUNCTION get_product_top_destinations(
  p_product_id UUID,
  p_days INT,
  p_prov_dept TEXT DEFAULT NULL,
  p_limit INT DEFAULT 15
) RETURNS TABLE(
  market_id UUID,
  market_name TEXT,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT
    so.market_id,
    dm.canonical_name::TEXT AS market_name,
    SUM(so.quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations so
  LEFT JOIN dim_market dm ON dm.id = so.market_id
  WHERE so.product_id = p_product_id
    AND so.market_id IS NOT NULL
    AND so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_prov_dept IS NULL OR COALESCE(so.provenance_dept_name, '') = p_prov_dept)
  GROUP BY so.market_id, dm.canonical_name
  ORDER BY SUM(so.quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION get_product_top_origins(
  p_product_id UUID,
  p_days INT,
  p_market_id UUID DEFAULT NULL,
  p_limit INT DEFAULT 15
) RETURNS TABLE(
  dept_name TEXT,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')::TEXT AS dept_name,
    SUM(quantity_kg)::NUMERIC AS total_kg
  FROM supply_observations
  WHERE product_id = p_product_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_market_id IS NULL OR market_id = p_market_id)
  GROUP BY COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')
  ORDER BY SUM(quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;

-- Time-binned daily totals for the supply-over-time line chart. One row
-- per observation_date in the window, already aggregated.
CREATE OR REPLACE FUNCTION get_product_supply_by_date(
  p_product_id UUID,
  p_days INT,
  p_market_id UUID DEFAULT NULL,
  p_prov_dept TEXT DEFAULT NULL
) RETURNS TABLE(
  observation_date DATE,
  total_kg NUMERIC
)
LANGUAGE sql STABLE AS $$
  SELECT observation_date, SUM(quantity_kg)::NUMERIC
  FROM supply_observations
  WHERE product_id = p_product_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_market_id IS NULL OR market_id = p_market_id)
    AND (p_prov_dept IS NULL OR COALESCE(provenance_dept_name, '') = p_prov_dept)
  GROUP BY observation_date
  ORDER BY observation_date ASC;
$$;

COMMENT ON FUNCTION get_market_supply_summary IS 'Aggregated supply totals for a market in a time window; used by market detail page supply section.';
COMMENT ON FUNCTION get_market_top_products IS 'Top N products by kg at a market (with optional origin filter) for the cross-filter UI.';
COMMENT ON FUNCTION get_market_top_provenance IS 'Top N origin depts for a market (with optional product filter).';
COMMENT ON FUNCTION get_product_supply_summary IS 'Aggregated supply totals for a product in a time window.';
COMMENT ON FUNCTION get_product_top_destinations IS 'Top N destination markets for a product (with optional origin filter).';
COMMENT ON FUNCTION get_product_top_origins IS 'Top N origin depts for a product (with optional market filter).';
COMMENT ON FUNCTION get_product_supply_by_date IS 'Daily supply totals for a product, already aggregated server-side.';
