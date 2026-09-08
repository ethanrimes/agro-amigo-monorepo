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
ALTER TABLE daily_price ADD COLUMN IF NOT EXISTS unit text NOT NULL DEFAULT 'kg';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS brand text NOT NULL DEFAULT '';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS registration text NOT NULL DEFAULT '';
ALTER TABLE input_price ADD COLUMN IF NOT EXISTS product_line text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS input_municipal_price (
 id text NOT NULL, department text NOT NULL, observed_on date NOT NULL, name text NOT NULL, category text NOT NULL,
 presentation text NOT NULL, price numeric NOT NULL CHECK(price>0), document_id text NOT NULL REFERENCES source_document(id),
 source_locator text NOT NULL, brand text NOT NULL DEFAULT '', registration text NOT NULL DEFAULT '', product_line text NOT NULL DEFAULT '',
 municipality text NOT NULL, PRIMARY KEY(id,department,municipality,observed_on)
);
CREATE INDEX IF NOT EXISTS input_price_recent ON input_price(observed_on,id,department);
CREATE INDEX IF NOT EXISTS input_municipal_recent ON input_municipal_price(observed_on,id,department,municipality);
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
 unit text NOT NULL,min_unit_price numeric,max_unit_price numeric,source_page integer NOT NULL,
 PRIMARY KEY(document_id,source_locator)
);
CREATE INDEX IF NOT EXISTS regional_price_lookup ON regional_price(product_id,market_name,observed_on DESC);
CREATE INDEX IF NOT EXISTS regional_price_date ON regional_price(observed_on DESC);
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
 FOREACH tab IN ARRAY ARRAY['price_observation','coffee_reference','coffee_factor','exchange_rate','daily_price','input_price','input_municipal_price','seasonal_year','historical_price','retained_record','source_document','source_pdf_page','source_archive_member','regional_price','input_reference_row','supply_observation'] LOOP
  IF to_regclass(tab) IS NULL THEN CONTINUE; END IF;
  EXECUTE format('DROP TRIGGER IF EXISTS retain_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
 FOREACH tab IN ARRAY ARRAY['historical_price','retained_record','source_document','source_pdf_page','source_archive_member','regional_price','input_reference_row'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
END $$;
GRANT SELECT ON historical_price,ingestion_run,ingestion_asset TO agro_reader;

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
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['source_ocr_scan','source_ocr_result','source_ocr_attempt'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS retain_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
  EXECUTE format('DROP TRIGGER IF EXISTS immutable_history ON %I',tab);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal()',tab);
 END LOOP;
END $$;
GRANT SELECT ON source_ocr_scan,source_ocr_task,source_ocr_result,source_ocr_attempt TO agro_reader;

CREATE TABLE IF NOT EXISTS regional_classification(document_id text REFERENCES source_document(id),source_locator text,category_path text[] NOT NULL,PRIMARY KEY(document_id,source_locator));
DROP TRIGGER IF EXISTS retain_history ON regional_classification;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON regional_classification FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON regional_classification;
CREATE TRIGGER immutable_history BEFORE UPDATE ON regional_classification FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON regional_classification TO agro_reader;

-- Retain invalidated versions, while removing them from public price results.
-- A corrected publisher file or independently dated PDF can replace the quote.
CREATE OR REPLACE VIEW published_price_observation AS
SELECT p.* FROM price_observation p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.status='review'
 AND (a.observed_on IS NULL OR a.observed_on=p.observed_on)
);
GRANT SELECT ON published_price_observation TO agro_reader;

CREATE OR REPLACE VIEW published_input_price AS
SELECT p.* FROM input_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.kind='inputs-pdf'
 AND a.processor_version='inputs-pdf-v4' AND p.source_locator NOT LIKE '%; inputs-pdf-v4'
);
CREATE OR REPLACE VIEW published_input_municipal_price AS
SELECT p.* FROM input_municipal_price p WHERE NOT EXISTS (
 SELECT 1 FROM ingestion_asset a WHERE a.document_id=p.document_id AND a.kind='inputs-pdf'
 AND a.processor_version='inputs-pdf-v4' AND p.source_locator NOT LIKE '%; inputs-pdf-v4'
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
DROP TRIGGER IF EXISTS retain_history ON official_price_quote;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON official_price_quote FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS immutable_history ON official_price_quote;
CREATE TRIGGER immutable_history BEFORE UPDATE ON official_price_quote FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS demo_window ON official_price_quote;
CREATE TRIGGER demo_window BEFORE INSERT ON official_price_quote FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
CREATE OR REPLACE VIEW published_official_price AS
 SELECT DISTINCT ON(q.quote_key,q.observed_on) q.* FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
 WHERE NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
 ORDER BY q.quote_key,q.observed_on,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator;
GRANT SELECT ON official_price_quote,published_official_price TO agro_reader;
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
CREATE INDEX IF NOT EXISTS input_municipal_locations_recent ON input_municipal_price(observed_on,department,municipality,id);
CREATE INDEX IF NOT EXISTS input_department_locations_recent ON input_price(observed_on,department,id);
CREATE INDEX IF NOT EXISTS ingestion_asset_document ON ingestion_asset(document_id);
CREATE INDEX IF NOT EXISTS input_price_catalog_cover ON input_price(id,observed_on DESC,price,department) INCLUDE(name,category,presentation,document_id,source_locator,brand,registration,product_line);
CREATE INDEX IF NOT EXISTS input_municipal_catalog_cover ON input_municipal_price(id,observed_on DESC,price,department,municipality) INCLUDE(name,category,presentation,document_id,source_locator,brand,registration,product_line);
