-- Migration: RPC function for CPC-wide latest department prices
-- Returns the most recent price per unique (department, casa_comercial, articulo, presentation)
-- for all products sharing a given CPC code. Collapses ~80K rows to ~1-3K.
-- Date: 2026-04-16

CREATE OR REPLACE FUNCTION get_cpc_latest_dept_prices(p_cpc_code TEXT)
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
    SELECT DISTINCT ON (ipd.department_id, ipd.casa_comercial_id, ipd.articulo, ipd.presentation)
        d.canonical_name::TEXT AS dept_name,
        ipd.dept_code::TEXT,
        ipd.articulo::TEXT,
        COALESCE(cc.canonical_name, '')::TEXT AS casa_comercial_name,
        ipd.presentation::TEXT,
        ipd.avg_price,
        ipd.price_date
    FROM insumo_prices_department ipd
    JOIN dim_department d ON d.id = ipd.department_id
    LEFT JOIN dim_casa_comercial cc ON cc.id = ipd.casa_comercial_id
    WHERE ipd.cpc_code = p_cpc_code
    ORDER BY ipd.department_id, ipd.casa_comercial_id, ipd.articulo, ipd.presentation, ipd.price_date DESC;
$$;

COMMENT ON FUNCTION get_cpc_latest_dept_prices IS 'Latest department-level price per unique (dept, casa_comercial, articulo, presentation) for a CPC code';
