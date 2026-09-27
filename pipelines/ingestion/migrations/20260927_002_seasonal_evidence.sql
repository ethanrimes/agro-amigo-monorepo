-- One representative document is insufficient for a year with revised sources.
ALTER TABLE seasonal_year ADD COLUMN IF NOT EXISTS source_documents jsonb NOT NULL DEFAULT '[]';
ALTER TABLE seasonal_year ADD COLUMN IF NOT EXISTS validation_version text;
ALTER TABLE seasonal_year ADD COLUMN IF NOT EXISTS review_reason text;
