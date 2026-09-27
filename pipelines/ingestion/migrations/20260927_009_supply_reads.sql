-- Production may build these indexes CONCURRENTLY, one at a time. History totals
-- need only indexed quantities/dates/identities, not large source_rows payloads.
CREATE INDEX IF NOT EXISTS supply_market_history_cover
 ON supply_observation(market_id,period_start,food_id)
 INCLUDE(product_id,observed_on,quantity_kg);
CREATE INDEX IF NOT EXISTS supply_product_history_cover
 ON supply_observation(product_id,period_start,market_id,food_id)
 INCLUDE(observed_on,quantity_kg) WHERE product_id IS NOT NULL;
