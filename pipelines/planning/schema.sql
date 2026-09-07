-- Immutable source bytes: an updated publisher URL creates a new hash, never overwrites evidence.
CREATE TABLE IF NOT EXISTS source_document (
 id text PRIMARY KEY CHECK (id ~ '^[a-f0-9]{64}$'), title text NOT NULL, publisher text NOT NULL,
 source_url text NOT NULL, media_type text NOT NULL, kind text NOT NULL CHECK (kind IN ('original','extract','methodology')),
 reference_period text NOT NULL, retrieved_at timestamptz NOT NULL DEFAULT now(),
 page_count integer, content bytea NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS document_alias (
 alias text PRIMARY KEY, document_id text NOT NULL REFERENCES source_document(id)
);
ALTER TABLE price_observation ADD COLUMN IF NOT EXISTS document_id text REFERENCES source_document(id);
ALTER TABLE price_observation ADD COLUMN IF NOT EXISTS source_locator text;
ALTER TABLE coffee_reference ADD COLUMN IF NOT EXISTS document_id text REFERENCES source_document(id);
ALTER TABLE coffee_factor ADD COLUMN IF NOT EXISTS document_id text REFERENCES source_document(id);
ALTER TABLE exchange_rate ADD COLUMN IF NOT EXISTS document_id text REFERENCES source_document(id);
CREATE TABLE IF NOT EXISTS municipality (
 id text PRIMARY KEY, name text NOT NULL, department text NOT NULL, department_id text NOT NULL,
 latitude double precision NOT NULL, longitude double precision NOT NULL, document_id text REFERENCES source_document(id)
);
CREATE TABLE IF NOT EXISTS crop_reference (
 municipality_id text REFERENCES municipality(id), crop_code text, crop text NOT NULL, variety text NOT NULL,
 reference_year integer NOT NULL, cycle text NOT NULL, physical_state text NOT NULL,
 planted_ha numeric NOT NULL, harvested_ha numeric NOT NULL, production_t numeric NOT NULL,
 yield_kg_ha numeric, document_id text NOT NULL REFERENCES source_document(id), source_rows jsonb NOT NULL,
 PRIMARY KEY(municipality_id,crop_code,reference_year)
);
CREATE TABLE IF NOT EXISTS crop_calendar (
 department_id text, crop text, activity text, reference_year integer, percentages jsonb NOT NULL,
 document_id text NOT NULL REFERENCES source_document(id), source_row integer NOT NULL,
 PRIMARY KEY(department_id,crop,activity,reference_year)
);
CREATE TABLE IF NOT EXISTS crop_suitability (
 municipality_id text REFERENCES municipality(id), crop_key text, classification text,
 area_ha numeric NOT NULL CHECK(area_ha>=0), document_id text NOT NULL REFERENCES source_document(id),
 PRIMARY KEY(municipality_id,crop_key,classification)
);
CREATE TABLE IF NOT EXISTS soil_reference (
 municipality_id text PRIMARY KEY REFERENCES municipality(id), samples integer NOT NULL, ph_samples integer NOT NULL,
 ph_median numeric, ph_low numeric, ph_high numeric, organic_matter_median numeric,
 oldest date, newest date, document_id text NOT NULL REFERENCES source_document(id)
);
-- Five COMPLETE calendar years, separately from the rolling current-price observations.
-- Each entry retains original nominal monthly prices and source rows; seasonal ratios pair months within a year.
CREATE TABLE IF NOT EXISTS seasonal_year (
 product_id text REFERENCES product(id), market_id text, reference_year integer,
 monthly_prices jsonb NOT NULL CHECK(jsonb_array_length(monthly_prices)=12),
 document_id text NOT NULL REFERENCES source_document(id), source_rows jsonb NOT NULL,
 PRIMARY KEY(product_id,market_id,reference_year)
);
CREATE TABLE IF NOT EXISTS cost_template (
 id text PRIMARY KEY, crop text NOT NULL, title text NOT NULL, region text NOT NULL,
 municipalities jsonb NOT NULL, reference_year integer NOT NULL, production_system text NOT NULL,
 yield_kg_ha numeric NOT NULL, costs jsonb NOT NULL, document_id text NOT NULL REFERENCES source_document(id),
 source_page integer NOT NULL, notes text NOT NULL
);
CREATE TABLE IF NOT EXISTS input_price (
 id text, department text, observed_on date, name text NOT NULL, category text NOT NULL,
 presentation text NOT NULL, price numeric NOT NULL CHECK(price>0),
 document_id text NOT NULL REFERENCES source_document(id), source_locator text NOT NULL,
 PRIMARY KEY(id,department,observed_on)
);
DROP TRIGGER IF EXISTS demo_window ON input_price;
CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON input_price FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
CREATE TABLE IF NOT EXISTS advisory (
 id text PRIMARY KEY, title text NOT NULL, summary text NOT NULL, action text NOT NULL,
 crops jsonb NOT NULL, departments jsonb NOT NULL, published_on date NOT NULL, valid_until date,
 kind text NOT NULL CHECK(kind IN ('official_alert','monitoring','reference')),
 document_id text NOT NULL REFERENCES source_document(id), source_page integer, source_url text NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_snapshot (
 id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{64}$'), latitude numeric NOT NULL CHECK(latitude BETWEEN -5 AND 14),
 longitude numeric NOT NULL CHECK(longitude BETWEEN -82 AND -66), fetched_at timestamptz NOT NULL DEFAULT now(),
 source_url text NOT NULL, payload jsonb NOT NULL CHECK(octet_length(payload::text)<65536)
);
CREATE INDEX IF NOT EXISTS weather_location ON weather_snapshot(latitude,longitude,fetched_at DESC);
GRANT SELECT ON source_document,document_alias,municipality,crop_reference,crop_calendar,crop_suitability,soil_reference,seasonal_year,cost_template,input_price,advisory,weather_snapshot TO agro_reader;
-- The application can append public forecast snapshots for provenance. No price/reference mutations.
GRANT INSERT ON weather_snapshot TO agro_reader;
