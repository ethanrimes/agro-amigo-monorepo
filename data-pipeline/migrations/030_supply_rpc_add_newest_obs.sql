-- Migration: Add newest_obs to the supply "top N" RPCs so the UI can show
-- the observation date alongside each bar/card without a second round trip.
--
-- Note: CREATE OR REPLACE FUNCTION cannot change the RETURNS TABLE signature
-- (PG raises 42P13), so we DROP then CREATE each one.
-- Date: 2026-04-16

DROP FUNCTION IF EXISTS get_market_top_products(UUID, INT, TEXT, INT);
DROP FUNCTION IF EXISTS get_market_top_provenance(UUID, INT, UUID, INT);
DROP FUNCTION IF EXISTS get_product_top_destinations(UUID, INT, TEXT, INT);
DROP FUNCTION IF EXISTS get_product_top_origins(UUID, INT, UUID, INT);

CREATE OR REPLACE FUNCTION get_market_top_products(
  p_market_id UUID,
  p_days INT,
  p_prov_dept TEXT DEFAULT NULL,
  p_limit INT DEFAULT 10
) RETURNS TABLE(
  product_id UUID,
  product_name TEXT,
  total_kg NUMERIC,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    so.product_id,
    dp.canonical_name::TEXT AS product_name,
    SUM(so.quantity_kg)::NUMERIC AS total_kg,
    MAX(so.observation_date) AS newest_obs
  FROM supply_observations so
  LEFT JOIN dim_product dp ON dp.id = so.product_id
  WHERE so.market_id = p_market_id
    AND so.observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_prov_dept IS NULL OR COALESCE(so.provenance_dept_name, '') = p_prov_dept)
  GROUP BY so.product_id, dp.canonical_name
  ORDER BY SUM(so.quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION get_market_top_provenance(
  p_market_id UUID,
  p_days INT,
  p_product_id UUID DEFAULT NULL,
  p_limit INT DEFAULT 15
) RETURNS TABLE(
  dept_name TEXT,
  total_kg NUMERIC,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')::TEXT AS dept_name,
    SUM(quantity_kg)::NUMERIC AS total_kg,
    MAX(observation_date) AS newest_obs
  FROM supply_observations
  WHERE market_id = p_market_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_product_id IS NULL OR product_id = p_product_id)
  GROUP BY COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')
  ORDER BY SUM(quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;

CREATE OR REPLACE FUNCTION get_product_top_destinations(
  p_product_id UUID,
  p_days INT,
  p_prov_dept TEXT DEFAULT NULL,
  p_limit INT DEFAULT 15
) RETURNS TABLE(
  market_id UUID,
  market_name TEXT,
  total_kg NUMERIC,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    so.market_id,
    dm.canonical_name::TEXT AS market_name,
    SUM(so.quantity_kg)::NUMERIC AS total_kg,
    MAX(so.observation_date) AS newest_obs
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
  total_kg NUMERIC,
  newest_obs DATE
)
LANGUAGE sql STABLE AS $$
  SELECT
    COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')::TEXT AS dept_name,
    SUM(quantity_kg)::NUMERIC AS total_kg,
    MAX(observation_date) AS newest_obs
  FROM supply_observations
  WHERE product_id = p_product_id
    AND observation_date >= CASE WHEN p_days > 0 THEN CURRENT_DATE - p_days ELSE DATE '1900-01-01' END
    AND (p_market_id IS NULL OR market_id = p_market_id)
  GROUP BY COALESCE(NULLIF(provenance_dept_name, ''), 'Desconocido')
  ORDER BY SUM(quantity_kg) DESC NULLS LAST
  LIMIT p_limit;
$$;
