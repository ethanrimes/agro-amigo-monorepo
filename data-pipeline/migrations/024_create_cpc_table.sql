-- Migration: Create CPC (Clasificación Central de Productos) reference table
-- Source: DANE CPC Ver. 2.1 Adaptada para Colombia (official public classification)
-- Date: 2026-04-15

-- CPC classification hierarchy table
-- Stores all levels: section, division, group, class, subclass, product
CREATE TABLE IF NOT EXISTS dim_cpc (
    code VARCHAR(10) PRIMARY KEY,
    title VARCHAR(1000) NOT NULL,
    level VARCHAR(10) NOT NULL CHECK (level IN ('section', 'division', 'group', 'class', 'subclass', 'product')),
    parent_code VARCHAR(10) REFERENCES dim_cpc(code),
    section_code VARCHAR(2),
    division_code VARCHAR(3),
    group_code VARCHAR(4),
    class_code VARCHAR(5),
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE dim_cpc IS 'CPC Ver. 2.1 A.C. — Clasificación Central de Productos adaptada para Colombia (DANE)';
COMMENT ON COLUMN dim_cpc.code IS 'CPC code (1-7 digits depending on level)';
COMMENT ON COLUMN dim_cpc.title IS 'Official Spanish title/description of the CPC code';
COMMENT ON COLUMN dim_cpc.level IS 'Hierarchy level: section > division > group > class > subclass > product';
COMMENT ON COLUMN dim_cpc.parent_code IS 'FK to parent CPC code in the hierarchy';
COMMENT ON COLUMN dim_cpc.section_code IS 'Ancestor section code (1 digit)';
COMMENT ON COLUMN dim_cpc.division_code IS 'Ancestor division code (2 digits)';
COMMENT ON COLUMN dim_cpc.group_code IS 'Ancestor group code (3 digits)';
COMMENT ON COLUMN dim_cpc.class_code IS 'Ancestor class code (4-5 digits)';

CREATE INDEX IF NOT EXISTS idx_cpc_level ON dim_cpc(level);
CREATE INDEX IF NOT EXISTS idx_cpc_parent ON dim_cpc(parent_code);
CREATE INDEX IF NOT EXISTS idx_cpc_section ON dim_cpc(section_code);

-- Add FK from dim_insumo to dim_cpc
ALTER TABLE dim_insumo ADD COLUMN IF NOT EXISTS cpc_id VARCHAR(10) REFERENCES dim_cpc(code);
CREATE INDEX IF NOT EXISTS idx_insumo_cpc ON dim_insumo(cpc_id);
