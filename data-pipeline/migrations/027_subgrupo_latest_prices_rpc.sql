-- Migration: RPC function for subgrupo-wide latest prices
-- Used on insumo detail pages when an insumo has NO CPC code — the UI falls
-- back to "all insumos in the same subgrupo" for the comparison table.
--
-- Source is insumo_prices_municipality (not _department) because DANE only
-- publishes municipality-level data for the categories that lack a CPC code
-- (propagation material, land rental, animal species, etc.). CPC-coded
-- categories like agrochemicals have dept-level detail with casa_comercial
-- and articulo — those already use get_cpc_latest_dept_prices (migration 025).
--
-- Return shape mirrors get_cpc_latest_dept_prices so the mobile/web UI can
-- reuse the same renderer:
--   articulo            -> insumo canonical_name (the "product" in the row)
--   casa_comercial_name -> municipio name when available (row-meta context)
--   dept_name, dept_code, presentation, avg_price, price_date as usual
--
-- Date: 2026-04-16

CREATE OR REPLACE FUNCTION get_subgrupo_latest_dept_prices(p_subgrupo_id UUID)
RETURNS TABLE(
    dept_name TEXT,
    dept_code TEXT,
    articulo TEXT,
    casa_comercial_name TEXT,
    presentation TEXT,
    avg_price NUMERIC,
    price_date DATE
)
LANGUAGE sql STABLE
AS $$
    SELECT DISTINCT ON (ipm.insumo_id, ipm.department_id, ipm.city_id, ipm.presentation)
        d.canonical_name::TEXT AS dept_name,
        ipm.dept_code::TEXT,
        i.canonical_name::TEXT AS articulo,
        COALESCE(c.canonical_name, '')::TEXT AS casa_comercial_name,
        ipm.presentation::TEXT,
        ipm.avg_price,
        ipm.price_date
    FROM insumo_prices_municipality ipm
    JOIN dim_insumo i ON i.id = ipm.insumo_id
    JOIN dim_department d ON d.id = ipm.department_id
    LEFT JOIN dim_city c ON c.id = ipm.city_id
    WHERE ipm.subgrupo_id = p_subgrupo_id
    ORDER BY ipm.insumo_id, ipm.department_id, ipm.city_id, ipm.presentation, ipm.price_date DESC;
$$;

COMMENT ON FUNCTION get_subgrupo_latest_dept_prices IS 'Latest muni-level price per (insumo, dept, muni, presentation) for a subgrupo — CPC-less fallback for insumo detail comparison table. Maps insumo canonical_name -> articulo, municipio -> casa_comercial_name to reuse CPC renderer.';
