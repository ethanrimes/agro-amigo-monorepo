-- Migration: Denormalize insumo grupo/subgrupo into proper dimension tables
-- Date: 2026-04-10

-- Insumo group dimension (e.g., Insumos agrícolas, Insumos pecuarios, Factores de producción)
CREATE TABLE IF NOT EXISTS dim_insumo_grupo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(200) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_insumo_grupo IS 'Top-level insumo groups (Insumos agrícolas, Insumos pecuarios, Factores de producción)';

-- Insumo subgroup dimension (e.g., Bioinsumos, Fertilizantes, Vitaminas)
CREATE TABLE IF NOT EXISTS dim_insumo_subgrupo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name VARCHAR(300) NOT NULL UNIQUE,
    grupo_id UUID NOT NULL REFERENCES dim_insumo_grupo(id),
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE dim_insumo_subgrupo IS 'Insumo subgroups, each mapping to one grupo';

-- Alias tables
CREATE TABLE IF NOT EXISTS alias_insumo_grupo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(200) NOT NULL UNIQUE,
    grupo_id UUID NOT NULL REFERENCES dim_insumo_grupo(id)
);

CREATE TABLE IF NOT EXISTS alias_insumo_subgrupo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value VARCHAR(300) NOT NULL UNIQUE,
    subgrupo_id UUID NOT NULL REFERENCES dim_insumo_subgrupo(id)
);

-- Add FK references to dim_insumo
ALTER TABLE dim_insumo ADD COLUMN IF NOT EXISTS grupo_id UUID REFERENCES dim_insumo_grupo(id);
ALTER TABLE dim_insumo ADD COLUMN IF NOT EXISTS subgrupo_id UUID REFERENCES dim_insumo_subgrupo(id);

-- Add FK references to price tables for direct queries
ALTER TABLE insumo_prices_municipality ADD COLUMN IF NOT EXISTS grupo_id UUID REFERENCES dim_insumo_grupo(id);
ALTER TABLE insumo_prices_municipality ADD COLUMN IF NOT EXISTS subgrupo_id UUID REFERENCES dim_insumo_subgrupo(id);
ALTER TABLE insumo_prices_department ADD COLUMN IF NOT EXISTS grupo_id UUID REFERENCES dim_insumo_grupo(id);
ALTER TABLE insumo_prices_department ADD COLUMN IF NOT EXISTS subgrupo_id UUID REFERENCES dim_insumo_subgrupo(id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_insumo_mun_grupo ON insumo_prices_municipality(grupo_id);
CREATE INDEX IF NOT EXISTS idx_insumo_mun_subgrupo ON insumo_prices_municipality(subgrupo_id);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_grupo ON insumo_prices_department(grupo_id);
CREATE INDEX IF NOT EXISTS idx_insumo_dep_subgrupo ON insumo_prices_department(subgrupo_id);
