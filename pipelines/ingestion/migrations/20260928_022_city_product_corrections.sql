-- Preserve every original city price row while publishing a verified product
-- identity from the same retained native PDF and exact source locator.
CREATE TABLE IF NOT EXISTS regional_price_product_correction (
 document_id text NOT NULL,
 source_locator text NOT NULL,
 old_product_id text NOT NULL,
 old_product_name text NOT NULL,
 corrected_product_id text NOT NULL REFERENCES product(id),
 corrected_product_name text NOT NULL,
 source_sha256 text NOT NULL CHECK(source_sha256=document_id),
 source_url text NOT NULL,
 source_page integer NOT NULL CHECK(source_page>0),
 verification jsonb NOT NULL CHECK(
   jsonb_typeof(verification)='object'
   AND verification->>'method'='native-pdf-glyph-spacing'
   AND verification ? 'unchanged_fields_sha256'
 ),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,source_locator),
 FOREIGN KEY(document_id,source_locator)
   REFERENCES regional_price(document_id,source_locator),
 CHECK(old_product_id<>corrected_product_id),
 CHECK(regexp_replace(old_product_name,'[[:space:]]+','','g')=
       regexp_replace(corrected_product_name,'[[:space:]]+','','g'))
);
CREATE INDEX IF NOT EXISTS regional_price_product_correction_new_lookup
 ON regional_price_product_correction(corrected_product_id,corrected_product_name,document_id,source_locator);

CREATE OR REPLACE FUNCTION validate_regional_price_product_correction()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original regional_price%ROWTYPE;
DECLARE source source_document%ROWTYPE;
BEGIN
 SELECT * INTO original FROM regional_price
 WHERE document_id=NEW.document_id AND source_locator=NEW.source_locator;
 SELECT * INTO source FROM source_document WHERE id=NEW.document_id;
 IF NOT FOUND OR source.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-pdf'
    OR source.source_url IS DISTINCT FROM NEW.source_url THEN
  RAISE EXCEPTION 'Correction must identify the exact archived city PDF source';
 END IF;
 IF original.product_id IS DISTINCT FROM NEW.old_product_id
    OR original.product_name IS DISTINCT FROM NEW.old_product_name
    OR original.source_page IS DISTINCT FROM NEW.source_page THEN
  RAISE EXCEPTION 'Correction does not match the immutable city price row';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_city_product_correction ON regional_price_product_correction;
CREATE TRIGGER validate_city_product_correction BEFORE INSERT ON regional_price_product_correction
 FOR EACH ROW EXECUTE FUNCTION validate_regional_price_product_correction();
DROP TRIGGER IF EXISTS immutable_history ON regional_price_product_correction;
CREATE TRIGGER immutable_history BEFORE UPDATE ON regional_price_product_correction
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON regional_price_product_correction;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON regional_price_product_correction
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();

-- UNION ALL keeps product-id filters indexable on both branches: ordinary rows
-- use regional_price_lookup, corrected rows use the correction lookup index.
CREATE OR REPLACE VIEW resolved_regional_price AS
 SELECT r.* FROM regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM regional_price_product_correction c
  WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator
 )
 UNION ALL
 SELECT r.document_id,r.source_locator,r.observed_on,
  c.corrected_product_id AS product_id,c.corrected_product_name AS product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,
  r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,
  r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN regional_price r
  ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
GRANT SELECT ON regional_price_product_correction,resolved_regional_price TO agro_reader;
GRANT SELECT,INSERT ON regional_price_product_correction TO agro_ingestor;
