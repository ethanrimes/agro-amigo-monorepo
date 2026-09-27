-- Derived current catalog only. Immutable originals, quotes/reviews stay intact.
CREATE TABLE IF NOT EXISTS official_catalog_current (
 quote_key text PRIMARY KEY,
 payload jsonb,
 dirty boolean NOT NULL DEFAULT true,
 version text NOT NULL DEFAULT '',
 refreshed_at timestamptz
);
CREATE INDEX IF NOT EXISTS official_catalog_dirty ON official_catalog_current(quote_key) WHERE dirty;
GRANT SELECT ON official_catalog_current TO agro_reader,agro_ingestor;
GRANT INSERT,UPDATE ON official_catalog_current TO agro_ingestor;

-- Transition tables deduplicate thousands of historical rows into their few
-- quote identities. Already-dirty keys never receive another physical update.
CREATE OR REPLACE FUNCTION dirty_official_quote_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO official_catalog_current(quote_key)
 SELECT DISTINCT quote_key FROM new_official_quotes ORDER BY quote_key
 ON CONFLICT(quote_key) DO UPDATE SET dirty=true WHERE NOT official_catalog_current.dirty;
 RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS official_catalog_quotes ON official_price_quote;
CREATE TRIGGER official_catalog_quotes AFTER INSERT ON official_price_quote
 REFERENCING NEW TABLE AS new_official_quotes FOR EACH STATEMENT EXECUTE FUNCTION dirty_official_quote_catalog();

CREATE OR REPLACE FUNCTION dirty_official_review_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO official_catalog_current(quote_key)
 SELECT DISTINCT q.quote_key FROM new_official_reviews r JOIN official_price_quote q
 ON q.document_id=r.document_id AND q.source_locator=r.source_locator
 ORDER BY q.quote_key
 ON CONFLICT(quote_key) DO UPDATE SET dirty=true WHERE NOT official_catalog_current.dirty;
 RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS official_catalog_reviews ON official_source_review;
CREATE TRIGGER official_catalog_reviews AFTER INSERT ON official_source_review
 REFERENCING NEW TABLE AS new_official_reviews FOR EACH STATEMENT EXECUTE FUNCTION dirty_official_review_catalog();

CREATE OR REPLACE FUNCTION dirty_official_asset_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_document text; current_document text;
BEGIN
 IF TG_OP='UPDATE' THEN
   IF NOT (OLD.status='review' OR NEW.status='review') OR
      (OLD.status,OLD.document_id,OLD.observed_on) IS NOT DISTINCT FROM (NEW.status,NEW.document_id,NEW.observed_on)
   THEN RETURN NULL; END IF;
 END IF;
 IF TG_OP<>'INSERT' AND OLD.status='review' THEN previous_document=OLD.document_id; END IF;
 IF TG_OP<>'DELETE' AND NEW.status='review' THEN current_document=NEW.document_id; END IF;
 IF previous_document IS NULL AND current_document IS NULL THEN RETURN NULL; END IF;
 INSERT INTO official_catalog_current(quote_key)
 SELECT DISTINCT quote_key FROM official_price_quote WHERE document_id IN (previous_document,current_document) ORDER BY quote_key
 ON CONFLICT(quote_key) DO UPDATE SET dirty=true WHERE NOT official_catalog_current.dirty;
 RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS official_catalog_assets ON ingestion_asset;
CREATE TRIGGER official_catalog_assets AFTER INSERT OR UPDATE OR DELETE ON ingestion_asset
 FOR EACH ROW EXECUTE FUNCTION dirty_official_asset_catalog();

-- Seed only missing identities. Reapplying the migration never dirties a clean
-- snapshot, while bounded periodic recovery can initialize an existing database.
INSERT INTO official_catalog_current(quote_key)
SELECT DISTINCT quote_key FROM official_price_quote
ON CONFLICT DO NOTHING;
