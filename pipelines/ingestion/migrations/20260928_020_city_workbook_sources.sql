-- Exact worksheet locators do not have a PDF page. Existing PDF originals and
-- rows remain unchanged. Fail quickly rather than wait behind a running import.
SET lock_timeout = '2s';
SET statement_timeout = '15s';
ALTER TABLE regional_price ALTER COLUMN source_page DROP NOT NULL;
