-- Run outside a transaction, after migration032 is valid/ready. It includes
-- the raw text and provenance required for the verified index-only plan.
DROP INDEX CONCURRENTLY IF EXISTS regional_quote_latest_cover;
