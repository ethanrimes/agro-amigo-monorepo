-- Migration: Normalize DIVIPOLA into separate departamentos and municipios tables
-- Description: Creates departamentos and municipios entities with proper foreign key relationship
-- Date: 2025-12-24

-- ============================================
-- 1. Create departamentos table
-- ============================================
CREATE TABLE IF NOT EXISTS departamentos (
    codigo_departamento VARCHAR(2) PRIMARY KEY,
    nombre_departamento VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add comments
COMMENT ON TABLE departamentos IS 'Colombian departments (DIVIPOLA reference data)';
COMMENT ON COLUMN departamentos.codigo_departamento IS 'DIVIPOLA department code (2 digits)';
COMMENT ON COLUMN departamentos.nombre_departamento IS 'Department name';

-- ============================================
-- 2. Create municipios table
-- ============================================
CREATE TABLE IF NOT EXISTS municipios (
    codigo_municipio VARCHAR(5) PRIMARY KEY,
    nombre_municipio VARCHAR(100) NOT NULL,
    codigo_departamento VARCHAR(2) NOT NULL REFERENCES departamentos(codigo_departamento) ON DELETE RESTRICT,
    tipo VARCHAR(50),
    longitud DECIMAL(12, 8),
    latitud DECIMAL(12, 8),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index on foreign key for query performance
CREATE INDEX IF NOT EXISTS idx_municipios_departamento ON municipios(codigo_departamento);

-- Add comments
COMMENT ON TABLE municipios IS 'Colombian municipalities (DIVIPOLA reference data)';
COMMENT ON COLUMN municipios.codigo_municipio IS 'DIVIPOLA municipality code (5 digits)';
COMMENT ON COLUMN municipios.nombre_municipio IS 'Municipality name';
COMMENT ON COLUMN municipios.codigo_departamento IS 'Foreign key to departamentos table';
COMMENT ON COLUMN municipios.tipo IS 'Type of administrative unit (Municipio, etc.)';
COMMENT ON COLUMN municipios.longitud IS 'Longitude coordinate';
COMMENT ON COLUMN municipios.latitud IS 'Latitude coordinate';

-- ============================================
-- 3. Populate departamentos from existing data
-- ============================================
INSERT INTO departamentos (codigo_departamento, nombre_departamento)
SELECT DISTINCT
    codigo_departamento,
    nombre_departamento
FROM divipola_municipios
WHERE codigo_departamento IS NOT NULL
ON CONFLICT (codigo_departamento) DO NOTHING;

-- ============================================
-- 4. Populate municipios from existing data
-- ============================================
INSERT INTO municipios (codigo_municipio, nombre_municipio, codigo_departamento, tipo, longitud, latitud)
SELECT
    codigo_municipio,
    nombre_municipio,
    codigo_departamento,
    tipo,
    longitud,
    latitud
FROM divipola_municipios
WHERE codigo_municipio IS NOT NULL
ON CONFLICT (codigo_municipio) DO NOTHING;

-- ============================================
-- 5. Enable Row-Level Security
-- ============================================
ALTER TABLE departamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE municipios ENABLE ROW LEVEL SECURITY;

-- Public read access for reference data
CREATE POLICY "Allow public read access to departamentos"
    ON departamentos FOR SELECT
    USING (true);

CREATE POLICY "Allow public read access to municipios"
    ON municipios FOR SELECT
    USING (true);

-- Service role full access
CREATE POLICY "Allow service role full access to departamentos"
    ON departamentos FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Allow service role full access to municipios"
    ON municipios FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
