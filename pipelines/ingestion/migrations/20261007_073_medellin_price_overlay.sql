-- Reviewed append-only price projection. DDL does not insert a correction or release a hold.
-- Retained source bytes, OCR readings, 160 raw prices and classifications remain
-- immutable. The exact two-row resolution is a later, separately reviewed insert.
DO $$ BEGIN
 IF to_regclass('public.city_pdf_publication_conflict') IS NULL
    OR to_regclass('public.verified_city_pdf_category_resolution') IS NULL
    OR to_regclass('public.regional_price') IS NULL
    OR to_regclass('public.source_ocr_result') IS NULL
 THEN RAISE EXCEPTION 'Prior city source/publication schema absent'; END IF;
END $$;

CREATE TABLE IF NOT EXISTS city_pdf_price_resolution (
 document_id text PRIMARY KEY REFERENCES source_document(id),
 conflict_id bigint NOT NULL UNIQUE REFERENCES city_pdf_publication_conflict(id),
 archive_id text NOT NULL REFERENCES source_document(id),
 entry_name text NOT NULL,
 source_url text NOT NULL,
 source_price_vector_sha256 text NOT NULL,
 stored_price_vector_sha256 text NOT NULL,
 stored_full17_sha256 text NOT NULL,
 classification_sha256 text NOT NULL,
 physical_review_sha256 text NOT NULL,
 proof_sha256 text NOT NULL,
 resolution_kind text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (document_id='cea9b437d3886fb18eeca6c6dca77f7b733c410bc46463df394e2f70f2453829'),
 CHECK (archive_id='503a044d44069e1bbb39d18f5082c86cc1489ad697c823c1345920cda56b8a2b'),
 CHECK (entry_name='Medellín, José María Villa 25-1-2024.pdf'),
 CHECK (source_url='https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip'),
 CHECK (source_price_vector_sha256='45be83b19b26db28d06458379cc80b72a93fbda19425e84d85e6f47c8fe97737'),
 CHECK (stored_price_vector_sha256='41bd005f8491fa483a5df0daa2f184e6feab7f9d31e2d35c2938eb121531ccfc'),
 CHECK (stored_full17_sha256='6ab3cab7b2644aeeb7487dd49fc1271d60decc9dca212a51e7d1e911530be740'),
 CHECK (classification_sha256='ea2998a1b01f5e66f158f39e449bc41972f8f42f73f8340612263ee370b7e0de'),
 CHECK (physical_review_sha256='d98abbbd7576a0ba5943135f8bc2f29239e4e426195b996c1e289fcc107838c2'),
 CHECK (proof_sha256='b5504237ee965a3ce3cb7f4b22e44b0474b415462a912638b7859d96e9cf07bd'),
 CHECK (resolution_kind='reviewed-retained-pdf-price-only')
);
CREATE TABLE IF NOT EXISTS city_pdf_price_overlay (
 document_id text NOT NULL REFERENCES city_pdf_price_resolution(document_id),
 source_locator text NOT NULL,
 prior_min_price numeric NOT NULL,prior_max_price numeric NOT NULL,
 prior_min_unit_price numeric NOT NULL,prior_max_unit_price numeric NOT NULL,
 corrected_min_price numeric NOT NULL,corrected_max_price numeric NOT NULL,
 corrected_min_unit_price numeric NOT NULL,corrected_max_unit_price numeric NOT NULL,
 PRIMARY KEY(document_id,source_locator),
 CHECK (corrected_min_price>0 AND corrected_max_price>=corrected_min_price),
 CHECK (corrected_min_unit_price>0 AND corrected_max_unit_price>=corrected_min_unit_price),
 CHECK (
   (source_locator='PDF page 3,table 1,row 46,round 2'
    AND prior_min_price=5800 AND prior_max_price=6000
    AND prior_min_unit_price=5800 AND prior_max_unit_price=6000
    AND corrected_min_price=6000 AND corrected_max_price=6000
    AND corrected_min_unit_price=6000 AND corrected_max_unit_price=6000)
   OR
   (source_locator='PDF page 3,table 1,row 48,round 2'
    AND prior_min_price=5000 AND prior_max_price=5300
    AND prior_min_unit_price=5000 AND prior_max_unit_price=5300
    AND corrected_min_price=5000 AND corrected_max_price=5000
    AND corrected_min_unit_price=5000 AND corrected_max_unit_price=5000)
 )
);

CREATE OR REPLACE FUNCTION validate_exact_city_pdf_price_resolution()
RETURNS trigger LANGUAGE plpgsql SET search_path=public,pg_catalog AS $$
DECLARE conflict city_pdf_publication_conflict%ROWTYPE;
DECLARE child source_document%ROWTYPE;
DECLARE parent source_document%ROWTYPE;
BEGIN
 SELECT * INTO conflict FROM city_pdf_publication_conflict WHERE id=NEW.conflict_id;
 SELECT * INTO child FROM source_document WHERE id=NEW.document_id;
 SELECT * INTO parent FROM source_document WHERE id=NEW.archive_id;
 IF conflict.document_id IS DISTINCT FROM NEW.document_id
    OR conflict.archive_id IS DISTINCT FROM NEW.archive_id
    OR conflict.entry_name IS DISTINCT FROM NEW.entry_name
    OR conflict.processor_version IS DISTINCT FROM 'city-v8:medellin-jan25-2024-price-only-hold-v1'
    OR conflict.native_sha256 IS DISTINCT FROM NEW.source_price_vector_sha256
    OR conflict.stored_sha256 IS DISTINCT FROM NEW.stored_price_vector_sha256
    OR conflict.details->>'scope' IS DISTINCT FROM 'printed-price-vector-only'
    OR conflict.details->>'other_13_fields_source_certified' IS DISTINCT FROM 'false'
    OR conflict.details->>'printed_positive_rounds' IS DISTINCT FROM '160'
    OR conflict.details->>'printed_price_matches' IS DISTINCT FROM '158'
    OR jsonb_array_length(conflict.details->'money_unit_field_differences') IS DISTINCT FROM 4
    OR (SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=NEW.document_id)<>1
    OR EXISTS (SELECT 1 FROM verified_city_pdf_category_resolution WHERE document_id=NEW.document_id)
    OR child.kind IS DISTINCT FROM 'original' OR child.media_type IS DISTINCT FROM 'application/pdf'
    OR child.source_url IS DISTINCT FROM NEW.source_url
    OR encode(sha256(child.content),'hex') IS DISTINCT FROM NEW.document_id
    OR child.metadata->>'archive_entry' IS DISTINCT FROM NEW.entry_name
    OR NOT (child.metadata->'parents' ? NEW.archive_id)
    OR parent.kind IS DISTINCT FROM 'original' OR parent.media_type IS DISTINCT FROM 'application/zip'
    OR parent.source_url IS DISTINCT FROM NEW.source_url
    OR encode(sha256(parent.content),'hex') IS DISTINCT FROM NEW.archive_id
    OR NOT EXISTS (SELECT 1 FROM source_archive_member m WHERE m.archive_id=NEW.archive_id
      AND m.entry_name=NEW.entry_name AND m.document_id=NEW.document_id)
    OR (SELECT count(*) FROM regional_price WHERE document_id=NEW.document_id)<>160
    OR (SELECT count(*) FROM regional_classification WHERE document_id=NEW.document_id)<>160
    OR (SELECT count(*) FROM source_ocr_task WHERE document_id=NEW.document_id AND status='published')<>4
    OR (SELECT count(*) FROM source_ocr_result r JOIN source_ocr_task t ON t.image_id=r.image_id
      WHERE t.document_id=NEW.document_id AND r.version='gemini-image-ocr-v2')<>8
    OR (SELECT count(*) FROM published_regional_price WHERE document_id=NEW.document_id)<>0
 THEN RAISE EXCEPTION 'Exact city PDF price resolution source/conflict changed'; END IF;
 IF NOT EXISTS (SELECT 1 FROM regional_price r WHERE r.document_id=NEW.document_id
     AND r.source_locator='PDF page 3,table 1,row 46,round 2' AND r.product_id='cilantro'
     AND r.observed_on='2024-01-25' AND r.quantity=1 AND r.unit='kg'
     AND r.min_price=5800 AND r.max_price=6000 AND r.min_unit_price=5800 AND r.max_unit_price=6000)
    OR NOT EXISTS (SELECT 1 FROM regional_price r WHERE r.document_id=NEW.document_id
     AND r.source_locator='PDF page 3,table 1,row 48,round 2' AND r.product_id='coliflor'
     AND r.observed_on='2024-01-25' AND r.quantity=1 AND r.unit='kg'
     AND r.min_price=5000 AND r.max_price=5300 AND r.min_unit_price=5000 AND r.max_unit_price=5300)
 THEN RAISE EXCEPTION 'Exact city PDF stored price facts changed'; END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION validate_exact_city_pdf_price_overlay()
RETURNS trigger LANGUAGE plpgsql SET search_path=public,pg_catalog AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM regional_price r WHERE r.document_id=NEW.document_id
    AND r.source_locator=NEW.source_locator AND r.observed_on='2024-01-25'
    AND r.presentation='Kilogramo' AND r.quantity=1 AND r.source_unit='Kilogramo' AND r.unit='kg'
    AND r.min_price=NEW.prior_min_price AND r.max_price=NEW.prior_max_price
    AND r.min_unit_price=NEW.prior_min_unit_price AND r.max_unit_price=NEW.prior_max_unit_price)
 THEN RAISE EXCEPTION 'Exact city PDF price overlay old row changed'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_exact_price_resolution ON city_pdf_price_resolution;
CREATE TRIGGER validate_exact_price_resolution BEFORE INSERT ON city_pdf_price_resolution
 FOR EACH ROW EXECUTE FUNCTION validate_exact_city_pdf_price_resolution();
DROP TRIGGER IF EXISTS validate_exact_price_overlay ON city_pdf_price_overlay;
CREATE TRIGGER validate_exact_price_overlay BEFORE INSERT ON city_pdf_price_overlay
 FOR EACH ROW EXECUTE FUNCTION validate_exact_city_pdf_price_overlay();
DROP TRIGGER IF EXISTS immutable_history ON city_pdf_price_resolution;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_pdf_price_resolution
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_pdf_price_resolution;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_pdf_price_resolution
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON city_pdf_price_overlay;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_pdf_price_overlay
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_pdf_price_overlay;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_pdf_price_overlay
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT ON city_pdf_price_resolution,city_pdf_price_overlay TO agro_ingestor;
GRANT SELECT ON city_pdf_price_resolution,city_pdf_price_overlay TO agro_reader;

-- A partial two-row insert remains held. Both fixed locators must be present.
CREATE OR REPLACE VIEW verified_city_pdf_price_resolution AS
 SELECT a.document_id,a.conflict_id FROM city_pdf_price_resolution a
 WHERE (SELECT count(*) FROM city_pdf_price_overlay o WHERE o.document_id=a.document_id)=2
   AND EXISTS (SELECT 1 FROM city_pdf_price_overlay o WHERE o.document_id=a.document_id
     AND o.source_locator='PDF page 3,table 1,row 46,round 2')
   AND EXISTS (SELECT 1 FROM city_pdf_price_overlay o WHERE o.document_id=a.document_id
     AND o.source_locator='PDF page 3,table 1,row 48,round 2');
CREATE OR REPLACE VIEW verified_city_pdf_price_overlay AS
 SELECT o.* FROM city_pdf_price_overlay o JOIN verified_city_pdf_price_resolution a
  ON a.document_id=o.document_id;
GRANT SELECT ON verified_city_pdf_price_resolution,verified_city_pdf_price_overlay TO agro_reader,agro_ingestor;
-- Publication cache keys include verified category and monetary resolutions.
GRANT SELECT ON verified_city_pdf_category_resolution TO agro_reader;

CREATE OR REPLACE VIEW unresolved_city_pdf_publication_conflict AS
 SELECT c.* FROM city_pdf_publication_conflict c WHERE NOT EXISTS (
  SELECT 1 FROM verified_city_pdf_category_resolution a
  WHERE a.conflict_id=c.id AND a.document_id=c.document_id)
 AND NOT EXISTS (
  SELECT 1 FROM verified_city_pdf_price_resolution a
  WHERE a.conflict_id=c.id AND a.document_id=c.document_id);
GRANT SELECT ON unresolved_city_pdf_publication_conflict TO agro_reader,agro_ingestor;

-- Keep all 18 columns, order and types of the existing public view. Only four
-- monetary cells at two exact source locators can differ from immutable raw.
CREATE OR REPLACE VIEW published_regional_price AS
 SELECT r.document_id,r.source_locator,r.observed_on,r.product_id,r.product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  coalesce(o.corrected_min_price,r.min_price) AS min_price,
  coalesce(o.corrected_max_price,r.max_price) AS max_price,r.unit,
  coalesce(o.corrected_min_unit_price,r.min_unit_price) AS min_unit_price,
  coalesce(o.corrected_max_unit_price,r.max_unit_price) AS max_unit_price,r.source_page
 FROM regional_price r LEFT JOIN verified_city_pdf_price_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator
 WHERE NOT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict c
  WHERE c.document_id=r.document_id OFFSET 0);
GRANT SELECT ON published_regional_price TO agro_reader,agro_ingestor;

-- Existing product and category corrections stay orthogonal. Money is already
-- projected by published_regional_price in both UNION arms.
CREATE OR REPLACE VIEW resolved_regional_price AS
 SELECT r.document_id,r.source_locator,r.observed_on,
  r.product_id,r.product_name,r.market_name,
  coalesce(o.corrected_category,r.category) AS category,
  r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
 FROM published_regional_price r
 LEFT JOIN verified_regional_category_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator
 WHERE NOT EXISTS (SELECT 1 FROM regional_price_product_correction c
  WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator)
 UNION ALL
 SELECT r.document_id,r.source_locator,r.observed_on,
  c.corrected_product_id AS product_id,c.corrected_product_name AS product_name,
  r.market_name,coalesce(o.corrected_category,r.category) AS category,
  r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
  r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r
  ON r.document_id=c.document_id AND r.source_locator=c.source_locator
 LEFT JOIN verified_regional_category_overlay o
  ON o.document_id=r.document_id AND o.source_locator=r.source_locator;
GRANT SELECT ON resolved_regional_price TO agro_reader,agro_ingestor;
