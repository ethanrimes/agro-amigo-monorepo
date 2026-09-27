-- Availability needs one newest retained date per location, without scanning
-- every product/month. Live rollout builds this same index CONCURRENTLY.
CREATE INDEX IF NOT EXISTS input_municipal_location_options
 ON input_municipal_price(department,municipality,observed_on DESC);
