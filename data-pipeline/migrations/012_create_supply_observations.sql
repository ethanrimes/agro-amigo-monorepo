-- Migration: Create supply_observations table for abastecimiento data
--            and add cpc_code column to dim_product
-- Date: 2026-04-10

-- Add CPC code to product dimension
ALTER TABLE dim_product ADD COLUMN IF NOT EXISTS cpc_code VARCHAR(20);
COMMENT ON COLUMN dim_product.cpc_code IS 'CPC (Central Product Classification) code from SIPSA abastecimiento';

-- Supply observations table - tracks quantities arriving at wholesale markets
CREATE TABLE IF NOT EXISTS supply_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_date DATE NOT NULL,

    -- Where it arrived (destination market)
    city_id UUID NOT NULL REFERENCES dim_city(id),
    market_id UUID REFERENCES dim_market(id),

    -- Where it came from (provenance)
    provenance_dept_code VARCHAR(5),
    provenance_muni_code VARCHAR(10),
    provenance_dept_name VARCHAR(200),
    provenance_muni_name VARCHAR(200),

    -- What product
    category_id UUID NOT NULL REFERENCES dim_category(id),
    product_id UUID NOT NULL REFERENCES dim_product(id),
    cpc_code VARCHAR(20),

    -- Quantity
    quantity_kg DECIMAL(14, 2) NOT NULL,

    -- Provenance
    source_path VARCHAR(500) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_supply_obs_date ON supply_observations(observation_date);
CREATE INDEX IF NOT EXISTS idx_supply_obs_city ON supply_observations(city_id);
CREATE INDEX IF NOT EXISTS idx_supply_obs_product ON supply_observations(product_id);
CREATE INDEX IF NOT EXISTS idx_supply_obs_category ON supply_observations(category_id);
CREATE INDEX IF NOT EXISTS idx_supply_obs_city_date ON supply_observations(city_id, observation_date);
CREATE INDEX IF NOT EXISTS idx_supply_obs_product_date ON supply_observations(product_id, observation_date);
CREATE INDEX IF NOT EXISTS idx_supply_obs_download ON supply_observations(download_entry_id);
CREATE INDEX IF NOT EXISTS idx_supply_obs_provenance ON supply_observations(provenance_dept_code, provenance_muni_code);

COMMENT ON TABLE supply_observations IS 'Supply/abastecimiento data: quantities of food arriving at wholesale markets';
COMMENT ON COLUMN supply_observations.provenance_dept_code IS 'DIVIPOLA department code where the food originated';
COMMENT ON COLUMN supply_observations.provenance_muni_code IS 'DIVIPOLA municipality code or ISO 3166-1 country code of origin';
