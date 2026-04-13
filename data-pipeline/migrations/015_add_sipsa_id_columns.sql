-- Migration: Add sipsa_id columns to dimension tables for SIPSA web service IDs
-- Date: 2026-04-11

-- Product ID in SIPSA system (artiId)
ALTER TABLE dim_product ADD COLUMN IF NOT EXISTS sipsa_id INTEGER;
COMMENT ON COLUMN dim_product.sipsa_id IS 'SIPSA web service product ID (artiId)';

-- Market ID in SIPSA system (fuenId)
ALTER TABLE dim_market ADD COLUMN IF NOT EXISTS sipsa_id INTEGER;
COMMENT ON COLUMN dim_market.sipsa_id IS 'SIPSA web service market/source ID (fuenId)';

-- Category ID in SIPSA system (futiId)
ALTER TABLE dim_category ADD COLUMN IF NOT EXISTS sipsa_id INTEGER;
COMMENT ON COLUMN dim_category.sipsa_id IS 'SIPSA web service category type ID (futiId)';

-- Insumo type ID in SIPSA system (tireId)
ALTER TABLE dim_insumo ADD COLUMN IF NOT EXISTS sipsa_id INTEGER;
COMMENT ON COLUMN dim_insumo.sipsa_id IS 'SIPSA web service insumo type ID (tireId)';

-- Create indexes for SIPSA ID lookups
CREATE INDEX IF NOT EXISTS idx_dim_product_sipsa_id ON dim_product(sipsa_id) WHERE sipsa_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dim_market_sipsa_id ON dim_market(sipsa_id) WHERE sipsa_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dim_category_sipsa_id ON dim_category(sipsa_id) WHERE sipsa_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dim_insumo_sipsa_id ON dim_insumo(sipsa_id) WHERE sipsa_id IS NOT NULL;
