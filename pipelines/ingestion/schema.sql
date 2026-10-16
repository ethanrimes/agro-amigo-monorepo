-- Permanent history. Application SELECTs retain their own recent-date filters.
CREATE OR REPLACE FUNCTION enforce_demo_window() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.observed_on > (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date THEN
  RAISE EXCEPTION 'Observation cannot be in the future';
 END IF;
 RETURN NEW;
END $$;
CREATE TABLE IF NOT EXISTS ingestion_run (
 id uuid PRIMARY KEY, mode text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, status text NOT NULL DEFAULT 'running', summary jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS ingestion_asset (
 url text PRIMARY KEY, kind text NOT NULL, observed_on date, discovered_at timestamptz NOT NULL DEFAULT now(),
 checked_at timestamptz, status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
 document_id text REFERENCES source_document(id), records integer NOT NULL DEFAULT 0, error text
);
ALTER TABLE ingestion_asset ADD COLUMN IF NOT EXISTS processor_version text NOT NULL DEFAULT '';
ALTER TABLE ingestion_asset ADD COLUMN IF NOT EXISTS http_etag text;
ALTER TABLE ingestion_asset ADD COLUMN IF NOT EXISTS http_last_modified text;
CREATE TABLE IF NOT EXISTS historical_price (
 document_id text NOT NULL REFERENCES source_document(id), source_locator text NOT NULL,
 series text NOT NULL, observed_on date NOT NULL, product_name text NOT NULL, market_name text NOT NULL,
 unit text NOT NULL, price numeric NOT NULL CHECK(price>0), change_percent numeric, details jsonb NOT NULL DEFAULT '{}',
 PRIMARY KEY(document_id,source_locator)
);
CREATE INDEX IF NOT EXISTS historical_price_lookup ON historical_price(series,observed_on,product_name);
-- Additive publication schema: exact source units and municipal prices.
ALTER TABLE price_observation DROP CONSTRAINT IF EXISTS price_observation_unit_check;
ALTER TABLE price_observation ADD CONSTRAINT price_observation_unit_check CHECK(unit IN ('kg','125kg','unit','litre'));
CREATE INDEX IF NOT EXISTS observation_directory_cover ON price_observation(observed_on DESC)
 INCLUDE(product_id,market_id,source_id,document_id,source_locator,period,unit);
ALTER TABLE daily_price ADD COLUMN IF NOT EXISTS unit text NOT NULL DEFAULT 'kg';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS brand text NOT NULL DEFAULT '';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS registration text NOT NULL DEFAULT '';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS product_line text NOT NULL DEFAULT '';
-- One old input link may resolve to several literal commercial lines. Retain
-- old IDs and prices; these append-only mappings never choose a winning line.
CREATE TABLE IF NOT EXISTS input_identity_alias (
 legacy_id text NOT NULL,id text NOT NULL,PRIMARY KEY(legacy_id,id),CHECK(legacy_id<>id)
);
GRANT SELECT,INSERT ON input_identity_alias TO agro_ingestor;
GRANT SELECT ON input_identity_alias TO agro_reader;
CREATE TABLE IF NOT EXISTS input_projection_supersession (
 old_document_id text NOT NULL REFERENCES source_document(id),
 old_source_locator text NOT NULL,
 old_id text NOT NULL,
 department text NOT NULL,
 observed_on date NOT NULL,
 name text NOT NULL,
 presentation text NOT NULL,
 price numeric NOT NULL,
 old_brand text NOT NULL,
 old_registration text NOT NULL,
 product_line text NOT NULL,
 replacement_document_id text NOT NULL REFERENCES source_document(id),
 replacement_source_locator text NOT NULL,
 replacement_id text NOT NULL,
 native_brand text NOT NULL CHECK (native_brand<>''),
 native_registration text NOT NULL CHECK (native_registration<>''),
 native_cells jsonb NOT NULL,
 reason text NOT NULL CHECK (reason<>''),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(old_document_id,old_source_locator,old_id,department,observed_on),
 CHECK(old_document_id<>replacement_document_id),
 CHECK(old_id<>replacement_id)
);
CREATE INDEX IF NOT EXISTS input_projection_supersession_old_id
 ON input_projection_supersession(old_id,department,observed_on);
GRANT SELECT,INSERT ON input_projection_supersession TO agro_ingestor;
GRANT SELECT ON input_projection_supersession TO agro_reader;
CREATE TABLE IF NOT EXISTS input_municipal_price (
 id text NOT NULL, department text NOT NULL, observed_on date NOT NULL, name text NOT NULL, category text NOT NULL,
 presentation text NOT NULL, price numeric NOT NULL CHECK(price>0), document_id text NOT NULL REFERENCES source_document(id),
 source_locator text NOT NULL, brand text NOT NULL DEFAULT '', registration text NOT NULL DEFAULT '', product_line text NOT NULL DEFAULT '',
 municipality text NOT NULL, PRIMARY KEY(id,department,municipality,observed_on)
);
CREATE INDEX IF NOT EXISTS input_price_recent ON input_price(observed_on,id,department);
CREATE INDEX IF NOT EXISTS input_municipal_recent ON input_municipal_price(observed_on,id,department,municipality);
CREATE INDEX IF NOT EXISTS input_municipal_location_options
 ON input_municipal_price(department,municipality,observed_on DESC);
CREATE TABLE IF NOT EXISTS source_pdf_page (
 document_id text REFERENCES source_document(id), page integer, text_content text NOT NULL,
 tables jsonb NOT NULL, extraction_version text NOT NULL, PRIMARY KEY(document_id,page,extraction_version)
);
DROP TRIGGER IF EXISTS demo_window ON input_municipal_price;
CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON input_municipal_price FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
CREATE TABLE IF NOT EXISTS source_archive_member (
 archive_id text REFERENCES source_document(id), entry_name text, document_id text REFERENCES source_document(id),
 PRIMARY KEY(archive_id,entry_name)
);
CREATE TABLE IF NOT EXISTS regional_price (
 document_id text REFERENCES source_document(id),source_locator text,observed_on date NOT NULL,
 product_id text NOT NULL,product_name text NOT NULL,market_name text NOT NULL,category text NOT NULL,
 presentation text NOT NULL,quantity numeric NOT NULL CHECK(quantity>0),source_unit text NOT NULL,
 round integer NOT NULL,round_label text NOT NULL,min_price numeric NOT NULL CHECK(min_price>0),max_price numeric NOT NULL CHECK(max_price>=min_price),
 unit text NOT NULL,min_unit_price numeric,max_unit_price numeric,source_page integer,
 PRIMARY KEY(document_id,source_locator)
);
CREATE INDEX IF NOT EXISTS regional_price_lookup ON regional_price(product_id,market_name,observed_on DESC);
CREATE INDEX IF NOT EXISTS regional_quote_latest_full_cover ON regional_price(
  product_id,market_name,lower(btrim(presentation)),quantity,
  lower(btrim(source_unit)),unit,observed_on DESC,round DESC)
  INCLUDE (presentation,source_unit,document_id,source_locator);
CREATE INDEX IF NOT EXISTS regional_price_date ON regional_price(observed_on DESC);
CREATE INDEX IF NOT EXISTS regional_market_directory_cover ON regional_price(observed_on DESC)
  INCLUDE (market_name, product_id, document_id, source_locator);
-- Native Excel city rows use worksheet/row locators without a PDF page.
ALTER TABLE regional_price ALTER COLUMN source_page DROP NOT NULL;
DROP TRIGGER IF EXISTS demo_window ON regional_price;
CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON regional_price FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
CREATE TABLE IF NOT EXISTS input_reference_row (
 document_id text REFERENCES source_document(id),source_locator text,kind text NOT NULL,observed_on date,
 name text NOT NULL,category text NOT NULL,details jsonb NOT NULL,PRIMARY KEY(document_id,source_locator)
);
CREATE INDEX IF NOT EXISTS input_reference_lookup ON input_reference_row(kind,observed_on DESC);
CREATE TABLE IF NOT EXISTS retained_record (
 table_name text NOT NULL, fingerprint text NOT NULL, captured_at timestamptz NOT NULL DEFAULT now(),
 record jsonb NOT NULL, PRIMARY KEY(table_name,fingerprint)
);
CREATE OR REPLACE FUNCTION preserve_record_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE value jsonb;
BEGIN
 IF TG_OP IN ('UPDATE','DELETE') THEN
  value=to_jsonb(OLD);
  INSERT INTO retained_record(table_name,fingerprint,record) VALUES(TG_TABLE_NAME,md5(value::text),value) ON CONFLICT DO NOTHING;
 END IF;
 IF TG_OP IN ('INSERT','UPDATE') THEN
  value=to_jsonb(NEW);
  INSERT INTO retained_record(table_name,fingerprint,record) VALUES(TG_TABLE_NAME,md5(value::text),value) ON CONFLICT DO NOTHING;
 END IF;
 RETURN NULL;
END $$;
CREATE OR REPLACE FUNCTION prevent_history_removal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Permanent historical data cannot be deleted or truncated'; END $$;
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['price_observation','coffee_reference','coffee_factor','exchange_rate','daily_price','input_price','input_municipal_price','seasonal_year','crop_reference','crop_calendar','crop_suitability','soil_reference','cost_template','advisory','supply_observation'] LOOP
  IF to_regclass(tab) IS NULL THEN CONTINUE; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=to_regclass(tab) AND tgname='preserve_versions') THEN
   EXECUTE format('INSERT INTO retained_record(table_name,fingerprint,record) SELECT %L,md5(to_jsonb(t)::text),to_jsonb(t) FROM %I t ON CONFLICT DO NOTHING',tab,tab);
  END IF;
  EXECUTE format('DROP TRIGGER IF EXISTS preserve_versions ON %I',tab);
  EXECUTE format('CREATE TRIGGER preserve_versions AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION preserve_record_version()',tab);
 END LOOP;
 FOREACH tab IN ARRAY ARRAY['price_observation','coffee_reference','coffee_factor','exchange_rate','daily_price','input_price','input_municipal_price','input_identity_alias','input_projection_supersession','seasonal_year','historical_price','retained_record','source_document','source_pdf_page','source_archive_member','regional_price','input_reference_row','supply_observation'] LOOP
  IF to_regclass(tab) IS NULL THEN CONTINUE; END IF;
  EXECUTE format('DROP TRIGGER IF EXISTS retain_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
 FOREACH tab IN ARRAY ARRAY['historical_price','retained_record','source_document','source_pdf_page','source_archive_member','regional_price','input_reference_row','input_identity_alias','input_projection_supersession'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
END $$;
GRANT SELECT ON historical_price,ingestion_run,ingestion_asset TO agro_reader;
-- Public source corrections and prior public price versions power source notes.
-- The application remains read-only; immutable-history protection is unchanged.
GRANT SELECT ON retained_record TO agro_reader;

GRANT SELECT ON input_municipal_price,source_pdf_page TO agro_reader;

GRANT SELECT ON regional_price,source_archive_member TO agro_reader;

GRANT SELECT ON input_reference_row TO agro_reader;

INSERT INTO source(id,name,url,frequency) VALUES
 ('dane-milk-farm','DANE SIPSA-L · leche cruda en finca','https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/boletin-mensual-precios-de-leche-cruda-en-finca','monthly'),
 ('dane-rice-mill','DANE SIPSA · arroz y subproductos en molinos','https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa','monthly') ON CONFLICT DO NOTHING;

-- OCR work is resumable; each provider transcription and rendered image is permanent.
CREATE TABLE IF NOT EXISTS source_ocr_scan(document_id text REFERENCES source_document(id),version text,scanned_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(document_id,version));
CREATE TABLE IF NOT EXISTS source_ocr_task(
 document_id text REFERENCES source_document(id),source_locator text,image_id text NOT NULL REFERENCES source_document(id),source_kind text,
 source_page integer,status text NOT NULL DEFAULT 'pending',created_at timestamptz NOT NULL DEFAULT now(),checked_at timestamptz,error text,
 PRIMARY KEY(document_id,source_locator));
CREATE INDEX IF NOT EXISTS source_ocr_pending ON source_ocr_task(status,created_at);
CREATE TABLE IF NOT EXISTS source_ocr_result(image_id text REFERENCES source_document(id),version text,reading integer,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(image_id,version,reading));
CREATE TABLE IF NOT EXISTS source_ocr_attempt(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,image_id text REFERENCES source_document(id),started_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS source_ocr_review_history(
 document_id text NOT NULL REFERENCES source_document(id),source_locator text NOT NULL,
 policy_version text NOT NULL,source_kind text NOT NULL,prior_status text NOT NULL,
 prior_error text,reading0_sha256 text NOT NULL CHECK(reading0_sha256 ~ '^[0-9a-f]{64}$'),
 reading1_sha256 text NOT NULL CHECK(reading1_sha256 ~ '^[0-9a-f]{64}$'),
 recorded_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,policy_version)
);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['source_ocr_scan','source_ocr_result','source_ocr_attempt','source_ocr_review_history'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS retain_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
END $$;
GRANT SELECT ON source_ocr_scan,source_ocr_task,source_ocr_result,source_ocr_attempt TO agro_reader;
GRANT SELECT,INSERT ON source_ocr_review_history TO agro_ingestor;
GRANT SELECT ON source_ocr_review_history TO agro_reader;

CREATE TABLE IF NOT EXISTS regional_classification(document_id text REFERENCES source_document(id),source_locator text,category_path text[] NOT NULL,PRIMARY KEY(document_id,source_locator));
DROP TRIGGER IF EXISTS retain_history ON regional_classification;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON regional_classification FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON regional_classification;
CREATE TRIGGER immutable_history BEFORE UPDATE ON regional_classification FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON regional_classification TO agro_reader;

CREATE TABLE IF NOT EXISTS price_observation_review (
 document_id text NOT NULL REFERENCES source_document(id), source_locator text NOT NULL,
 product_id text NOT NULL, market_id text NOT NULL, source_id text NOT NULL,
 observed_on date NOT NULL, period text NOT NULL, unit text NOT NULL,
 reason text NOT NULL, evidence jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,product_id,market_id,source_id,observed_on,period,unit)
);
DROP TRIGGER IF EXISTS retain_history ON price_observation_review;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON price_observation_review
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON price_observation_review;
CREATE TRIGGER immutable_history BEFORE UPDATE ON price_observation_review
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON price_observation_review TO agro_reader;
GRANT SELECT,INSERT ON price_observation_review TO agro_ingestor;

-- Retain invalidated versions, while removing them from public price results.
-- A corrected publisher file or independently dated PDF can replace the quote.
CREATE OR REPLACE VIEW published_price_observation AS
SELECT p.* FROM price_observation p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.status='review'
 AND (a.observed_on IS NULL OR a.observed_on=p.observed_on)
) AND NOT EXISTS (
 SELECT 1 FROM price_observation_review r
 WHERE r.document_id=p.document_id AND r.source_locator=p.source_locator
 AND r.product_id=p.product_id AND r.market_id=p.market_id AND r.source_id=p.source_id
 AND r.observed_on=p.observed_on AND r.period=p.period AND r.unit=p.unit
);
GRANT SELECT ON published_price_observation TO agro_reader;

-- Also declared by the additive automation migration; needed before the views
-- when installing this schema into a new database.
CREATE TABLE IF NOT EXISTS ingestion_checkpoint (
 document_id text NOT NULL REFERENCES source_document(id),processor_version text NOT NULL,
 step text NOT NULL,records bigint NOT NULL DEFAULT 0,completed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,processor_version,step)
);
GRANT SELECT,INSERT ON ingestion_checkpoint TO agro_ingestor;
GRANT SELECT ON ingestion_checkpoint TO agro_reader;

CREATE OR REPLACE VIEW published_input_price AS
SELECT p.* FROM input_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
) AND NOT EXISTS (
 SELECT 1 FROM input_identity_alias a JOIN input_price replacement ON replacement.id=a.id
 WHERE a.legacy_id=p.id AND replacement.department=p.department
 AND replacement.observed_on=p.observed_on
 AND (replacement.name,replacement.presentation,replacement.brand,replacement.registration,replacement.product_line)
   IS NOT DISTINCT FROM (p.name,p.presentation,p.brand,p.registration,p.product_line)
 AND (SELECT retrieved_at FROM source_document WHERE id=replacement.document_id)
   >= (SELECT retrieved_at FROM source_document WHERE id=p.document_id)
)
AND NOT EXISTS (
 SELECT 1 FROM input_projection_supersession s
 JOIN input_price replacement ON replacement.id=s.replacement_id
  AND replacement.department=s.department
  AND replacement.observed_on=s.observed_on
  AND replacement.document_id=s.replacement_document_id
  AND replacement.source_locator=s.replacement_source_locator
 JOIN source_document old_doc ON old_doc.id=s.old_document_id
 JOIN source_document new_doc ON new_doc.id=s.replacement_document_id
 WHERE p.document_id=s.old_document_id
  AND p.source_locator=s.old_source_locator
  AND p.id=s.old_id
  AND p.department=s.department
  AND p.observed_on=s.observed_on
  AND (p.name,p.presentation,p.price,p.brand,p.registration,p.product_line)
    IS NOT DISTINCT FROM
      (s.name,s.presentation,s.price,s.old_brand,s.old_registration,s.product_line)
  AND (replacement.name,replacement.presentation,replacement.price,
       replacement.brand,replacement.registration,replacement.product_line)
    IS NOT DISTINCT FROM
      (s.name,s.presentation,s.price,s.native_brand,s.native_registration,s.product_line)
  AND old_doc.source_url=new_doc.source_url
  AND new_doc.retrieved_at>=old_doc.retrieved_at
);
CREATE OR REPLACE VIEW published_input_municipal_price AS
SELECT p.* FROM input_municipal_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=p.document_id
 AND c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
 AND substring(c.processor_version from '([0-9]+)$')::numeric
   > coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0)
) AND NOT EXISTS (
 SELECT 1 FROM input_identity_alias a JOIN input_municipal_price replacement ON replacement.id=a.id
 WHERE a.legacy_id=p.id AND replacement.department=p.department
 AND replacement.municipality=p.municipality AND replacement.observed_on=p.observed_on
 AND (replacement.name,replacement.presentation,replacement.brand,replacement.registration,replacement.product_line)
   IS NOT DISTINCT FROM (p.name,p.presentation,p.brand,p.registration,p.product_line)
 AND (SELECT retrieved_at FROM source_document WHERE id=replacement.document_id)
   >= (SELECT retrieved_at FROM source_document WHERE id=p.document_id)
);
GRANT SELECT ON published_input_price,published_input_municipal_price TO agro_reader;

-- Official alternative sources have explicit currencies, markets and price bases.
-- Every source revision and parser result stays immutable; publication selects
-- the latest valid version of each exact dated quote identity.
CREATE TABLE IF NOT EXISTS official_price_quote (
 document_id text NOT NULL REFERENCES source_document(id),source_locator text NOT NULL,parser_version text NOT NULL,
 quote_key text NOT NULL,product_id text NOT NULL,product_name text NOT NULL,category text NOT NULL,publisher text NOT NULL,
 series text NOT NULL,basis text NOT NULL,currency text NOT NULL CHECK(currency IN ('COP','USD','EUR','GBP')),
 unit text NOT NULL,market text NOT NULL,observed_on date NOT NULL,period_start date,
 price numeric NOT NULL CHECK(price>0),min_price numeric,max_price numeric,source_page integer,
 details jsonb NOT NULL DEFAULT '{}',parsed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,parser_version),
 CHECK(min_price IS NULL OR min_price>0),CHECK(max_price IS NULL OR max_price>0),
 CHECK(min_price IS NULL OR max_price IS NULL OR min_price<=max_price)
);
CREATE INDEX IF NOT EXISTS official_quote_identity ON official_price_quote(quote_key,observed_on DESC);
CREATE INDEX IF NOT EXISTS official_quote_products ON official_price_quote(product_id,observed_on DESC);
CREATE INDEX IF NOT EXISTS official_quote_document_revisions ON official_price_quote(document_id,source_locator,parsed_at DESC) INCLUDE(observed_on,parser_version);
DROP TRIGGER IF EXISTS retain_history ON official_price_quote;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON official_price_quote FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON official_price_quote;
CREATE TRIGGER immutable_history BEFORE UPDATE ON official_price_quote FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS demo_window ON official_price_quote;
CREATE TRIGGER demo_window BEFORE INSERT ON official_price_quote FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
CREATE TABLE IF NOT EXISTS official_source_review (
 document_id text REFERENCES source_document(id),source_locator text,parser_version text,
 record jsonb NOT NULL,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(document_id,source_locator,parser_version)
);
DROP TRIGGER IF EXISTS retain_history ON official_source_review;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON official_source_review FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON official_source_review;
CREATE TRIGGER immutable_history BEFORE UPDATE ON official_source_review FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON official_source_review TO agro_reader;
-- A later parser can withdraw an ambiguous quote without changing its evidence.
-- A subsequent corrected parse can publish again, preserving all revisions.
CREATE OR REPLACE VIEW published_official_price AS
 SELECT DISTINCT ON(q.quote_key,q.observed_on) q.*
 FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
 WHERE NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
   AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
 AND NOT EXISTS(SELECT 1 FROM official_source_review r
   WHERE r.document_id=q.document_id AND r.source_locator=q.source_locator
     AND r.created_at>=q.parsed_at)
 AND NOT EXISTS(SELECT 1 FROM official_price_quote newer
   WHERE newer.document_id=q.document_id AND newer.source_locator=q.source_locator
     AND newer.parsed_at>q.parsed_at)
 ORDER BY q.quote_key,q.observed_on,CASE WHEN q.series='dane-milk-macroregion'
      AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
      AND COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period) IN (
        to_char(q.observed_on,'YYYY-MM-DD'),
        to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
    THEN COALESCE(NULLIF(q.details->>'bulletin_period',''),d.reference_period)
    END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator;
GRANT SELECT ON published_official_price TO agro_reader;
CREATE INDEX IF NOT EXISTS input_municipal_locations_recent ON input_municipal_price(observed_on,department,municipality,id);
CREATE INDEX IF NOT EXISTS input_department_locations_recent ON input_price(observed_on,department,id);
CREATE INDEX IF NOT EXISTS ingestion_asset_document ON ingestion_asset(document_id);
CREATE INDEX IF NOT EXISTS input_price_catalog_cover ON input_price(id,observed_on DESC,price,department) INCLUDE(name,category,presentation,document_id,source_locator,brand,registration,product_line);
CREATE INDEX IF NOT EXISTS input_municipal_catalog_cover ON input_municipal_price(id,observed_on DESC,price,department,municipality) INCLUDE(name,category,presentation,document_id,source_locator,brand,registration,product_line);
CREATE INDEX IF NOT EXISTS official_quote_history_cover ON official_price_quote(quote_key,observed_on DESC) INCLUDE(document_id,source_locator,parser_version,parsed_at,series);
-- Append display corrections without modifying immutable source metadata/bytes.
CREATE TABLE IF NOT EXISTS source_document_annotation (
 annotation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 field text NOT NULL CHECK(field='reference_period'),
 original_value text NOT NULL,
 corrected_value text NOT NULL CHECK(btrim(corrected_value)<>''),
 reason text NOT NULL CHECK(btrim(reason)<>''),
 native_locators text[] NOT NULL CHECK(cardinality(native_locators)>0
   AND array_position(native_locators,NULL) IS NULL),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(document_id,field,corrected_value,reason,native_locators)
);
CREATE INDEX IF NOT EXISTS source_document_annotation_latest
 ON source_document_annotation(document_id,field,annotation_id DESC);
CREATE OR REPLACE FUNCTION validate_source_document_annotation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE original_period text;
BEGIN
 IF NEW.field<>'reference_period' THEN
  RAISE EXCEPTION 'Unsupported source metadata annotation field';
 END IF;
 SELECT reference_period INTO original_period FROM source_document WHERE id=NEW.document_id;
 IF NOT FOUND OR NEW.original_value IS DISTINCT FROM original_period THEN
  RAISE EXCEPTION 'Annotation must identify the exact immutable original value';
 END IF;
 IF EXISTS(SELECT 1 FROM unnest(NEW.native_locators) locator WHERE btrim(locator)='') THEN
  RAISE EXCEPTION 'Annotation requires nonempty native source locators';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS validate_annotation ON source_document_annotation;
CREATE TRIGGER validate_annotation BEFORE INSERT ON source_document_annotation
 FOR EACH ROW EXECUTE FUNCTION validate_source_document_annotation();
DROP TRIGGER IF EXISTS immutable_history ON source_document_annotation;
CREATE TRIGGER immutable_history BEFORE UPDATE ON source_document_annotation
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON source_document_annotation;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON source_document_annotation
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON source_document_annotation TO agro_reader;
GRANT SELECT,INSERT ON source_document_annotation TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE source_document_annotation_annotation_id_seq TO agro_ingestor;
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

-- Immutable child-PDF conflicts block public reads until a later audited,
-- append-only full-field correction and resolution mechanism is installed.
CREATE TABLE IF NOT EXISTS city_pdf_publication_conflict (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 archive_id text REFERENCES source_document(id),
 entry_name text,
 processor_version text NOT NULL,
 native_sha256 text NOT NULL CHECK (native_sha256 ~ '^[0-9a-f]{64}$'),
 stored_sha256 text NOT NULL CHECK (stored_sha256 ~ '^[0-9a-f]{64}$'),
 details jsonb NOT NULL CHECK (jsonb_typeof(details)='object'),
 detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(document_id,processor_version,native_sha256,stored_sha256)
);
CREATE INDEX IF NOT EXISTS city_pdf_publication_conflict_document
 ON city_pdf_publication_conflict(document_id);
DROP TRIGGER IF EXISTS immutable_history ON city_pdf_publication_conflict;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_pdf_publication_conflict
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_pdf_publication_conflict;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_pdf_publication_conflict
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_pdf_publication_conflict TO agro_reader;
GRANT SELECT,INSERT ON city_pdf_publication_conflict TO agro_ingestor;
GRANT USAGE,SELECT ON SEQUENCE city_pdf_publication_conflict_id_seq TO agro_ingestor;

CREATE OR REPLACE VIEW published_regional_price AS
 SELECT r.* FROM regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM city_pdf_publication_conflict conflict
  WHERE conflict.document_id=r.document_id OFFSET 0
 );
GRANT SELECT ON published_regional_price TO agro_reader;

-- UNION ALL keeps product-id filters indexable on both branches: ordinary rows
-- use regional_price_lookup, corrected rows use the correction lookup index.
CREATE OR REPLACE VIEW resolved_regional_price AS
 SELECT r.* FROM published_regional_price r WHERE NOT EXISTS (
  SELECT 1 FROM regional_price_product_correction c
  WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator
 )
 UNION ALL
 SELECT r.document_id,r.source_locator,r.observed_on,
  c.corrected_product_id AS product_id,c.corrected_product_name AS product_name,
  r.market_name,r.category,r.presentation,r.quantity,r.source_unit,r.round,
  r.round_label,r.min_price,r.max_price,r.unit,r.min_unit_price,
  r.max_unit_price,r.source_page
 FROM regional_price_product_correction c JOIN published_regional_price r
  ON r.document_id=c.document_id AND r.source_locator=c.source_locator;
GRANT SELECT ON regional_price_product_correction,resolved_regional_price TO agro_reader;
-- Immutable, versioned evidence that an archived city PDF was checked for
-- native product-column spacing. Retry rows are nonterminal and cool down.
CREATE TABLE IF NOT EXISTS city_product_scan (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id text NOT NULL REFERENCES source_document(id),
 scan_version text NOT NULL,
 status text NOT NULL CHECK(status IN ('complete','review','retry')),
 source_sha256 text NOT NULL CHECK(source_sha256=document_id),
 source_url text NOT NULL,
 storage text,
 candidate_rows integer NOT NULL DEFAULT 0 CHECK(candidate_rows>=0),
 inserted_rows integer NOT NULL DEFAULT 0 CHECK(inserted_rows>=0),
 reason_code text,
 scanned_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(inserted_rows<=candidate_rows),
 CHECK((status='complete' AND reason_code IS NULL) OR
       (status<>'complete' AND reason_code IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS city_product_scan_terminal
 ON city_product_scan(document_id,scan_version)
 WHERE status IN ('complete','review');
CREATE INDEX IF NOT EXISTS city_product_scan_retry_recent
 ON city_product_scan(document_id,scan_version,scanned_at DESC)
 WHERE status='retry';
DROP TRIGGER IF EXISTS immutable_history ON city_product_scan;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_product_scan
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_product_scan;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_product_scan
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_product_scan TO agro_reader;
-- Return only a reader-active boolean to the writer. The SECURITY DEFINER
-- owner must have pg_read_all_stats; do not grant that broad role to ingestion.
CREATE OR REPLACE FUNCTION public.agro_readers_active()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog AS $$
  SELECT EXISTS (
    SELECT 1 FROM pg_catalog.pg_stat_activity
    WHERE usename = 'agro_reader' AND state = 'active'
  );
$$;
DO $$ BEGIN
  IF NOT pg_catalog.pg_has_role(
    (SELECT pg_catalog.pg_get_userbyid(proowner) FROM pg_catalog.pg_proc
     WHERE oid='public.agro_readers_active()'::pg_catalog.regprocedure),
    'pg_read_all_stats','member'
  ) THEN
    RAISE EXCEPTION 'agro_readers_active owner cannot observe reader state';
  END IF;
END $$;
REVOKE ALL ON FUNCTION public.agro_readers_active() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.agro_readers_active() TO agro_ingestor;
