-- Migration 022: Enable RLS on all remaining tables
-- Date: 2026-04-15
--
-- Policy pattern:
--   Public (anon): SELECT only on dimension, alias, and observation tables
--   Service role: ALL access on every table
--   No public access on internal pipeline tables

-- ============================================================
-- DIMENSION TABLES -- public read, service write
-- ============================================================

ALTER TABLE dim_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_subcategory ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_product ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_department ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_city ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_market ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_presentation ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_casa_comercial ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_insumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_insumo_grupo ENABLE ROW LEVEL SECURITY;
ALTER TABLE dim_insumo_subgrupo ENABLE ROW LEVEL SECURITY;

-- Public read
DROP POLICY IF EXISTS "Public read dim_category" ON dim_category;
CREATE POLICY "Public read dim_category" ON dim_category FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_subcategory" ON dim_subcategory;
CREATE POLICY "Public read dim_subcategory" ON dim_subcategory FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_product" ON dim_product;
CREATE POLICY "Public read dim_product" ON dim_product FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_department" ON dim_department;
CREATE POLICY "Public read dim_department" ON dim_department FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_city" ON dim_city;
CREATE POLICY "Public read dim_city" ON dim_city FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_market" ON dim_market;
CREATE POLICY "Public read dim_market" ON dim_market FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_presentation" ON dim_presentation;
CREATE POLICY "Public read dim_presentation" ON dim_presentation FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_units" ON dim_units;
CREATE POLICY "Public read dim_units" ON dim_units FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_casa_comercial" ON dim_casa_comercial;
CREATE POLICY "Public read dim_casa_comercial" ON dim_casa_comercial FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_insumo" ON dim_insumo;
CREATE POLICY "Public read dim_insumo" ON dim_insumo FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_insumo_grupo" ON dim_insumo_grupo;
CREATE POLICY "Public read dim_insumo_grupo" ON dim_insumo_grupo FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read dim_insumo_subgrupo" ON dim_insumo_subgrupo;
CREATE POLICY "Public read dim_insumo_subgrupo" ON dim_insumo_subgrupo FOR SELECT USING (true);

-- Service role full access on dimension tables
DROP POLICY IF EXISTS "Service full dim_category" ON dim_category;
CREATE POLICY "Service full dim_category" ON dim_category FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_subcategory" ON dim_subcategory;
CREATE POLICY "Service full dim_subcategory" ON dim_subcategory FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_product" ON dim_product;
CREATE POLICY "Service full dim_product" ON dim_product FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_department" ON dim_department;
CREATE POLICY "Service full dim_department" ON dim_department FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_city" ON dim_city;
CREATE POLICY "Service full dim_city" ON dim_city FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_market" ON dim_market;
CREATE POLICY "Service full dim_market" ON dim_market FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_presentation" ON dim_presentation;
CREATE POLICY "Service full dim_presentation" ON dim_presentation FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_units" ON dim_units;
CREATE POLICY "Service full dim_units" ON dim_units FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_casa_comercial" ON dim_casa_comercial;
CREATE POLICY "Service full dim_casa_comercial" ON dim_casa_comercial FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_insumo" ON dim_insumo;
CREATE POLICY "Service full dim_insumo" ON dim_insumo FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_insumo_grupo" ON dim_insumo_grupo;
CREATE POLICY "Service full dim_insumo_grupo" ON dim_insumo_grupo FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full dim_insumo_subgrupo" ON dim_insumo_subgrupo;
CREATE POLICY "Service full dim_insumo_subgrupo" ON dim_insumo_subgrupo FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- ALIAS TABLES -- no public access (internal mapping), service only
-- ============================================================

ALTER TABLE alias_category ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_subcategory ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_product ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_city ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_market ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_presentation ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_casa_comercial ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_insumo ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_insumo_grupo ENABLE ROW LEVEL SECURITY;
ALTER TABLE alias_insumo_subgrupo ENABLE ROW LEVEL SECURITY;

-- Service role full access only (no public read -- these are pipeline internals)
DROP POLICY IF EXISTS "Service full alias_category" ON alias_category;
CREATE POLICY "Service full alias_category" ON alias_category FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_subcategory" ON alias_subcategory;
CREATE POLICY "Service full alias_subcategory" ON alias_subcategory FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_product" ON alias_product;
CREATE POLICY "Service full alias_product" ON alias_product FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_city" ON alias_city;
CREATE POLICY "Service full alias_city" ON alias_city FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_market" ON alias_market;
CREATE POLICY "Service full alias_market" ON alias_market FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_presentation" ON alias_presentation;
CREATE POLICY "Service full alias_presentation" ON alias_presentation FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_units" ON alias_units;
CREATE POLICY "Service full alias_units" ON alias_units FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_casa_comercial" ON alias_casa_comercial;
CREATE POLICY "Service full alias_casa_comercial" ON alias_casa_comercial FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_insumo" ON alias_insumo;
CREATE POLICY "Service full alias_insumo" ON alias_insumo FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_insumo_grupo" ON alias_insumo_grupo;
CREATE POLICY "Service full alias_insumo_grupo" ON alias_insumo_grupo FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full alias_insumo_subgrupo" ON alias_insumo_subgrupo;
CREATE POLICY "Service full alias_insumo_subgrupo" ON alias_insumo_subgrupo FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- OBSERVATION / FACT TABLES -- public read, service write
-- ============================================================

ALTER TABLE price_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE supply_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE insumo_prices_department ENABLE ROW LEVEL SECURITY;
ALTER TABLE insumo_prices_municipality ENABLE ROW LEVEL SECURITY;

-- Public read
DROP POLICY IF EXISTS "Public read price_observations" ON price_observations;
CREATE POLICY "Public read price_observations" ON price_observations FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read supply_observations" ON supply_observations;
CREATE POLICY "Public read supply_observations" ON supply_observations FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read insumo_prices_department" ON insumo_prices_department;
CREATE POLICY "Public read insumo_prices_department" ON insumo_prices_department FOR SELECT USING (true);
DROP POLICY IF EXISTS "Public read insumo_prices_municipality" ON insumo_prices_municipality;
CREATE POLICY "Public read insumo_prices_municipality" ON insumo_prices_municipality FOR SELECT USING (true);

-- Service role full access
DROP POLICY IF EXISTS "Service full price_observations" ON price_observations;
CREATE POLICY "Service full price_observations" ON price_observations FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full supply_observations" ON supply_observations;
CREATE POLICY "Service full supply_observations" ON supply_observations FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full insumo_prices_department" ON insumo_prices_department;
CREATE POLICY "Service full insumo_prices_department" ON insumo_prices_department FOR ALL USING (auth.role() = 'service_role');
DROP POLICY IF EXISTS "Service full insumo_prices_municipality" ON insumo_prices_municipality;
CREATE POLICY "Service full insumo_prices_municipality" ON insumo_prices_municipality FOR ALL USING (auth.role() = 'service_role');
