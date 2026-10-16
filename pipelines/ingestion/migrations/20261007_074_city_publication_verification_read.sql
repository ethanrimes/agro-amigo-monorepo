-- Ingestion verifies the public projection before and after publication holds.
-- This grants read access only; original prices and source files stay retained.
GRANT SELECT ON published_regional_price TO agro_ingestor;
