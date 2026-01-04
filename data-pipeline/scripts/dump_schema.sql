-- dump_schema.sql
-- Dumps the current backend schema to a CSV file for Claude context
--
-- Usage:
--   psql $SUPABASE_DB_URL -f scripts/dump_schema.sql
--
-- Output: ./schema_columns.csv
\copy (SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'public' AND table_name IN ('departamentos', 'divipola_municipios', 'download_entries', 'download_errors', 'extracted_pdfs', 'municipios', 'processed_prices', 'processing_errors', 'schema_migrations') ORDER BY table_name, ordinal_position) TO './schema_columns.csv' WITH CSV HEADER;

-- Also output a summary view
\echo '=== Table Summary ==='
SELECT
    table_name,
    COUNT(*) as column_count
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name IN ('departamentos', 'divipola_municipios', 'download_entries', 'download_errors', 'extracted_pdfs', 'municipios', 'processed_prices', 'processing_errors', 'schema_migrations')
GROUP BY table_name
ORDER BY table_name;
