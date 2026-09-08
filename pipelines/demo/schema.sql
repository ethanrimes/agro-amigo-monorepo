CREATE TABLE IF NOT EXISTS source (
 id text PRIMARY KEY, name text NOT NULL, url text NOT NULL, frequency text NOT NULL
);
CREATE TABLE IF NOT EXISTS product (
 id text PRIMARY KEY, name text NOT NULL, category text NOT NULL, image_key text NOT NULL DEFAULT 'produce', priority integer NOT NULL DEFAULT 100
);
CREATE TABLE IF NOT EXISTS market (
 id text PRIMARY KEY, name text NOT NULL, city text NOT NULL, region text NOT NULL
);
CREATE TABLE IF NOT EXISTS price_observation (
 product_id text REFERENCES product(id), market_id text REFERENCES market(id), source_id text REFERENCES source(id),
 observed_on date NOT NULL, period text NOT NULL CHECK(period IN ('daily','monthly')), unit text NOT NULL CHECK(unit IN ('kg','125kg')),
 price numeric(16,2) NOT NULL CHECK(price>0), min_price numeric(16,2), max_price numeric(16,2),
 source_url text NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(product_id,market_id,source_id,observed_on,period,unit),
 CHECK(min_price IS NULL OR min_price<=price), CHECK(max_price IS NULL OR max_price>=price)
);
CREATE INDEX IF NOT EXISTS observation_lookup ON price_observation(product_id,observed_on DESC);
CREATE INDEX IF NOT EXISTS observation_window ON price_observation(observed_on,source_id);
CREATE INDEX IF NOT EXISTS market_region ON market(region);
CREATE TABLE IF NOT EXISTS coffee_reference (
 observed_on date PRIMARY KEY, price numeric(16,2) NOT NULL CHECK(price>0), source_url text NOT NULL,
 fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS coffee_factor (
 observed_on date NOT NULL, factor integer NOT NULL CHECK(factor BETWEEN 70 AND 120), price numeric(16,2) NOT NULL CHECK(price>0), source_url text NOT NULL,
 PRIMARY KEY(observed_on,factor)
);
CREATE TABLE IF NOT EXISTS exchange_rate (
 observed_on date PRIMARY KEY, valid_until date NOT NULL, price numeric(12,4) NOT NULL CHECK(price>0), source_url text NOT NULL,
 CHECK(valid_until>=observed_on)
);
-- No fabricated buyer quotes. Reserved for future authenticated, verified suppliers.
CREATE TABLE IF NOT EXISTS buyer_offer (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), buyer_name text NOT NULL, product_id text REFERENCES product(id),
 observed_on date NOT NULL, valid_until date NOT NULL, price numeric(16,2) NOT NULL CHECK(price>0),
 unit text NOT NULL CHECK(unit IN ('kg','125kg')), quality_terms text NOT NULL, delivery_location text NOT NULL,
 minimum_kg numeric(16,2) NOT NULL CHECK(minimum_kg>0), payment_terms text NOT NULL,
 verification_status text NOT NULL DEFAULT 'unverified' CHECK(verification_status IN ('unverified','verified','withdrawn')),
 source_url text NOT NULL, CHECK(valid_until>=observed_on)
);
CREATE TABLE IF NOT EXISTS import_run (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, imported_at timestamptz NOT NULL DEFAULT now(),
 window_start date NOT NULL, window_end date NOT NULL, summary jsonb NOT NULL
);
CREATE OR REPLACE FUNCTION enforce_demo_window() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.observed_on>(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date THEN
  RAISE EXCEPTION 'Observation cannot be in the future';
 END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['price_observation','coffee_reference','coffee_factor','exchange_rate','buyer_offer'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS demo_window ON %I',tab);
  EXECUTE format('CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_demo_window()',tab);
 END LOOP;
END $$;
