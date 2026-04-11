-- Migration: Create insumos (agricultural input) price tables
-- Date: 2026-04-10

-- Dimension table for casa comercial (commercial brand)
CREATE TABLE IF NOT EXISTS dim_casa_comercial (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(300) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_casa_comercial IS 'Commercial brand/company for agricultural inputs';

-- Alias table for casa comercial string variants
CREATE TABLE IF NOT EXISTS alias_casa_comercial (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(300) NOT NULL UNIQUE,
    casa_comercial_id UUID NOT NULL REFERENCES dim_casa_comercial(id)
);

-- Dimension table for insumo product names
CREATE TABLE IF NOT EXISTS dim_insumo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(300) NOT NULL UNIQUE,
    grupo VARCHAR(200),        -- Group (Insumos agrícolas, Insumos pecuarios, etc.)
    subgrupo VARCHAR(200),     -- Subgroup (Bioinsumos, Fertilizantes, etc.)
    cpc_code VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_insumo IS 'Agricultural input/insumo product dimension';

-- Alias table for insumo product name variants
CREATE TABLE IF NOT EXISTS alias_insumo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(300) NOT NULL UNIQUE,
    insumo_id UUID NOT NULL REFERENCES dim_insumo(id)
);

-- Municipality-level insumo prices
CREATE TABLE IF NOT EXISTS insumo_prices_municipality (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    price_date DATE NOT NULL,       -- First of month
    department_id UUID NOT NULL REFERENCES dim_department(id),
    city_id UUID REFERENCES dim_city(id),
    dept_code VARCHAR(5),
    muni_code VARCHAR(10),
    insumo_id UUID NOT NULL REFERENCES dim_insumo(id),
    presentation VARCHAR(200),
    avg_price DECIMAL(14, 2),
    source_path VARCHAR(500) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insumo_mun_date ON insumo_prices_municipality(price_date);
CREATE INDEX IF NOT EXISTS idx_insumo_mun_product ON insumo_prices_municipality(insumo_id);
CREATE INDEX IF NOT EXISTS idx_insumo_mun_dept ON insumo_prices_municipality(department_id);
CREATE INDEX IF NOT EXISTS idx_insumo_mun_city ON insumo_prices_municipality(city_id);
CREATE INDEX IF NOT EXISTS idx_insumo_mun_download ON insumo_prices_municipality(download_entry_id);

COMMENT ON TABLE insumo_prices_municipality IS 'Agricultural input prices at municipality level';

-- Department-level insumo prices (has additional detail: Casa Comercial, Artículo, Registro ICA)
CREATE TABLE IF NOT EXISTS insumo_prices_department (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    price_date DATE NOT NULL,       -- First of month
    department_id UUID NOT NULL REFERENCES dim_department(id),
    dept_code VARCHAR(5),
    insumo_id UUID NOT NULL REFERENCES dim_insumo(id),
    articulo VARCHAR(300),
    casa_comercial_id UUID REFERENCES dim_casa_comercial(id),
    registro_ica VARCHAR(50),
    cpc_code VARCHAR(20),
    presentation VARCHAR(200),
    avg_price DECIMAL(14, 2),
    source_path VARCHAR(500) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insumo_dep_date ON insumo_prices_department(price_date);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_product ON insumo_prices_department(insumo_id);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_dept ON insumo_prices_department(department_id);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_casa ON insumo_prices_department(casa_comercial_id);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_download ON insumo_prices_department(download_entry_id);

COMMENT ON TABLE insumo_prices_department IS 'Agricultural input prices at department level with commercial brand detail';
