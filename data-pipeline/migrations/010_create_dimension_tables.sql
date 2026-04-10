-- Migration: Create dimension tables for entity disambiguation
-- Description: Normalized dimension tables for product taxonomy and geography,
--              with alias mapping tables to resolve string variants.
-- Date: 2026-04-10

-- ============================================================
-- PRODUCT TAXONOMY DIMENSIONS
-- Hierarchy: product -> subcategory -> category
-- ============================================================

-- Categories (top-level product grouping)
CREATE TABLE IF NOT EXISTS dim_category (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_category IS 'Canonical product categories (e.g. Frutas, Verduras y hortalizas)';

-- Subcategories (mid-level, each belongs to exactly one category)
CREATE TABLE IF NOT EXISTS dim_subcategory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    category_id UUID NOT NULL REFERENCES dim_category(id),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_subcategory IS 'Canonical subcategories, each mapping to one category';

-- Products (leaf level, each belongs to exactly one subcategory)
CREATE TABLE IF NOT EXISTS dim_product (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(300) NOT NULL UNIQUE,
    subcategory_id UUID NOT NULL REFERENCES dim_subcategory(id),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_product IS 'Canonical product names, each mapping to one subcategory';

-- Presentations (packaging type - independent dimension)
CREATE TABLE IF NOT EXISTS dim_presentation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_presentation IS 'Canonical presentation/packaging types (e.g. Kilogramo, Bulto)';

-- Units (weight/quantity spec - independent dimension)
CREATE TABLE IF NOT EXISTS dim_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_units IS 'Canonical unit specifications (e.g. 1 Kilogramo, 50 Kilogramo)';

-- ============================================================
-- GEOGRAPHY DIMENSIONS
-- Hierarchy: market -> city -> department
-- Department and city IDs come from divipola_municipios.
-- ============================================================

-- Departments
CREATE TABLE IF NOT EXISTS dim_department (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    divipola_code VARCHAR(2),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_department IS 'Canonical departments, linked to DIVIPOLA codes';

-- Cities (each belongs to exactly one department)
CREATE TABLE IF NOT EXISTS dim_city (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    department_id UUID NOT NULL REFERENCES dim_department(id),
    divipola_code VARCHAR(5),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_city IS 'Canonical city names, each mapping to one department';

-- Markets (each belongs to exactly one city)
CREATE TABLE IF NOT EXISTS dim_market (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    city_id UUID NOT NULL REFERENCES dim_city(id),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_market IS 'Canonical market names, each mapping to one city';

-- ============================================================
-- ALIAS MAPPING TABLES
-- Map every raw string variant to its canonical dimension entity.
-- ============================================================

CREATE TABLE IF NOT EXISTS alias_category (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    category_id UUID NOT NULL REFERENCES dim_category(id)
);

CREATE TABLE IF NOT EXISTS alias_subcategory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    subcategory_id UUID NOT NULL REFERENCES dim_subcategory(id)
);

CREATE TABLE IF NOT EXISTS alias_product (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(300) NOT NULL UNIQUE,
    product_id UUID NOT NULL REFERENCES dim_product(id)
);

CREATE TABLE IF NOT EXISTS alias_presentation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    presentation_id UUID NOT NULL REFERENCES dim_presentation(id)
);

CREATE TABLE IF NOT EXISTS alias_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(100) NOT NULL UNIQUE,
    units_id UUID NOT NULL REFERENCES dim_units(id)
);

CREATE TABLE IF NOT EXISTS alias_city (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    city_id UUID NOT NULL REFERENCES dim_city(id)
);

CREATE TABLE IF NOT EXISTS alias_market (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    market_id UUID NOT NULL REFERENCES dim_market(id)
);

-- ============================================================
-- NORMALIZED PRICE OBSERVATIONS
-- References only UUIDs into dimension tables.
-- Subcategory, category, city, department are derivable from
-- product_id and market_id/city_id via the hierarchy, but stored
-- denormalized for query performance.
-- ============================================================

CREATE TABLE IF NOT EXISTS price_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    price_date DATE NOT NULL,
    round INTEGER DEFAULT 1,
    min_price DECIMAL(12, 2),
    max_price DECIMAL(12, 2),

    -- Product taxonomy (all filled via hierarchy from product_id)
    category_id UUID NOT NULL REFERENCES dim_category(id),
    subcategory_id UUID NOT NULL REFERENCES dim_subcategory(id),
    product_id UUID NOT NULL REFERENCES dim_product(id),
    presentation_id UUID REFERENCES dim_presentation(id),
    units_id UUID REFERENCES dim_units(id),

    -- Geography (all filled via hierarchy from market_id or city_id)
    department_id UUID NOT NULL REFERENCES dim_department(id),
    city_id UUID NOT NULL REFERENCES dim_city(id),
    market_id UUID REFERENCES dim_market(id),

    -- Provenance
    source_type VARCHAR(20) NOT NULL,
    source_path VARCHAR(500) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),
    extracted_pdf_id UUID REFERENCES extracted_pdfs(id),
    processed_price_id UUID REFERENCES processed_prices(id),

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_price_obs_date ON price_observations(price_date);
CREATE INDEX IF NOT EXISTS idx_price_obs_product ON price_observations(product_id);
CREATE INDEX IF NOT EXISTS idx_price_obs_city ON price_observations(city_id);
CREATE INDEX IF NOT EXISTS idx_price_obs_market ON price_observations(market_id);
CREATE INDEX IF NOT EXISTS idx_price_obs_category ON price_observations(category_id);
CREATE INDEX IF NOT EXISTS idx_price_obs_city_date ON price_observations(city_id, price_date);
CREATE INDEX IF NOT EXISTS idx_price_obs_product_date ON price_observations(product_id, price_date);
CREATE INDEX IF NOT EXISTS idx_price_obs_download ON price_observations(download_entry_id);

COMMENT ON TABLE price_observations IS 'Normalized price observations with UUID references to dimension tables';
COMMENT ON COLUMN price_observations.processed_price_id IS 'Link back to the original processed_prices row';
