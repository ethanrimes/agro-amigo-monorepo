-- Migration: Add RLS policies to all tables
-- Description: Row Level Security policies for data access control
-- Date: 2024-12-24

-- Enable RLS on all tables
ALTER TABLE divipola_municipios ENABLE ROW LEVEL SECURITY;
ALTER TABLE download_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_pdfs ENABLE ROW LEVEL SECURITY;
ALTER TABLE processed_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_errors ENABLE ROW LEVEL SECURITY;

-- ==================== DIVIPOLA Policies ====================
-- Public read access for reference data (everyone can read municipalities)
DROP POLICY IF EXISTS "Public read access for divipola" ON divipola_municipios;
CREATE POLICY "Public read access for divipola"
ON divipola_municipios FOR SELECT
USING (true);

-- Service role can insert/update (for initial data load)
DROP POLICY IF EXISTS "Service role can modify divipola" ON divipola_municipios;
CREATE POLICY "Service role can modify divipola"
ON divipola_municipios FOR ALL
USING (auth.role() = 'service_role');

-- ==================== Download Entries Policies ====================
-- Service role full access (for pipeline operations)
DROP POLICY IF EXISTS "Service role full access download_entries" ON download_entries;
CREATE POLICY "Service role full access download_entries"
ON download_entries FOR ALL
USING (auth.role() = 'service_role');

-- Public read access for transparency
DROP POLICY IF EXISTS "Public read access for download_entries" ON download_entries;
CREATE POLICY "Public read access for download_entries"
ON download_entries FOR SELECT
USING (true);

-- ==================== Extracted PDFs Policies ====================
-- Service role full access
DROP POLICY IF EXISTS "Service role full access extracted_pdfs" ON extracted_pdfs;
CREATE POLICY "Service role full access extracted_pdfs"
ON extracted_pdfs FOR ALL
USING (auth.role() = 'service_role');

-- Public read access
DROP POLICY IF EXISTS "Public read access for extracted_pdfs" ON extracted_pdfs;
CREATE POLICY "Public read access for extracted_pdfs"
ON extracted_pdfs FOR SELECT
USING (true);

-- ==================== Processed Prices Policies ====================
-- Service role full access
DROP POLICY IF EXISTS "Service role full access processed_prices" ON processed_prices;
CREATE POLICY "Service role full access processed_prices"
ON processed_prices FOR ALL
USING (auth.role() = 'service_role');

-- Public read access for price data
DROP POLICY IF EXISTS "Public read access for processed_prices" ON processed_prices;
CREATE POLICY "Public read access for processed_prices"
ON processed_prices FOR SELECT
USING (true);

-- ==================== Processing Errors Policies ====================
-- Service role full access
DROP POLICY IF EXISTS "Service role full access processing_errors" ON processing_errors;
CREATE POLICY "Service role full access processing_errors"
ON processing_errors FOR ALL
USING (auth.role() = 'service_role');

-- Restrict error visibility to service role only (contains debugging info)
-- No public access policy for processing_errors
