-- Migration: Create divipola_municipios table
-- Description: Colombian municipalities reference table from DIVIPOLA
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS divipola_municipios (
    id SERIAL PRIMARY KEY,
    codigo_departamento VARCHAR(2) NOT NULL,
    nombre_departamento VARCHAR(100) NOT NULL,
    codigo_municipio VARCHAR(5) NOT NULL UNIQUE,
    nombre_municipio VARCHAR(100) NOT NULL,
    tipo VARCHAR(50),
    longitud DECIMAL(12, 8),
    latitud DECIMAL(12, 8),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_divipola_departamento ON divipola_municipios(codigo_departamento);
CREATE INDEX IF NOT EXISTS idx_divipola_municipio_nombre ON divipola_municipios(nombre_municipio);

-- Add comments
COMMENT ON TABLE divipola_municipios IS 'Colombian municipalities reference data from DIVIPOLA';
COMMENT ON COLUMN divipola_municipios.codigo_departamento IS 'Department code (2 digits)';
COMMENT ON COLUMN divipola_municipios.nombre_departamento IS 'Department name';
COMMENT ON COLUMN divipola_municipios.codigo_municipio IS 'Municipality code (5 digits, unique)';
COMMENT ON COLUMN divipola_municipios.nombre_municipio IS 'Municipality name';
COMMENT ON COLUMN divipola_municipios.tipo IS 'Type: Municipio, Isla, Área no municipalizada';
COMMENT ON COLUMN divipola_municipios.longitud IS 'Longitude coordinate';
COMMENT ON COLUMN divipola_municipios.latitud IS 'Latitude coordinate';
