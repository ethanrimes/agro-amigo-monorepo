-- Migration: Add RLS to unrestricted tables
-- Description: Enable RLS on download_errors and schema_migrations tables
-- Date: 2025-01-18

-- ==================== Enable RLS ====================
ALTER TABLE download_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;

-- ==================== Download Errors Policies ====================
-- Service role full access (for pipeline operations)
DROP POLICY IF EXISTS "Service role full access download_errors" ON download_errors;
CREATE POLICY "Service role full access download_errors"
ON download_errors FOR ALL
USING (auth.role() = 'service_role');

-- No public access for download_errors (contains debugging info)

-- ==================== Schema Migrations Policies ====================
-- Service role full access (for running migrations)
DROP POLICY IF EXISTS "Service role full access schema_migrations" ON schema_migrations;
CREATE POLICY "Service role full access schema_migrations"
ON schema_migrations FOR ALL
USING (auth.role() = 'service_role');

-- No public access for schema_migrations (internal tracking table)
