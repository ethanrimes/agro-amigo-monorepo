-- Monthly aggregates of exact, dated DANE arrivals. Source names are preserved.
ALTER TABLE market ADD COLUMN IF NOT EXISTS municipality_id text REFERENCES municipality(id);
CREATE TABLE IF NOT EXISTS supply_observation (
 market_id text NOT NULL REFERENCES market(id), food_id text NOT NULL, food_name text NOT NULL,
 product_id text REFERENCES product(id), category text NOT NULL,
 period_start date NOT NULL, observed_on date NOT NULL, first_reported_on date NOT NULL,
 quantity_kg numeric NOT NULL CHECK(quantity_kg>=0), reporting_days integer NOT NULL CHECK(reporting_days>0),
 document_id text NOT NULL REFERENCES source_document(id), source_rows jsonb NOT NULL,
 PRIMARY KEY(market_id,food_id,period_start), CHECK(first_reported_on<=observed_on)
);
CREATE INDEX IF NOT EXISTS supply_product_date ON supply_observation(product_id,observed_on DESC);
CREATE INDEX IF NOT EXISTS supply_market_date ON supply_observation(market_id,observed_on DESC);
DROP TRIGGER IF EXISTS demo_window ON supply_observation;
CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON supply_observation FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
GRANT SELECT ON supply_observation TO agro_reader;
