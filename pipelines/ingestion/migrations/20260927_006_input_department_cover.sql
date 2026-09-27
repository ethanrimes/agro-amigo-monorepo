-- On a live database create this index CONCURRENTLY outside a transaction,
-- then verify pg_index.indisvalid before deploying the scoped catalog query.
-- Includes match the existing input catalog cover, with department first so a
-- scoped catalog can read current/prior prices without one lookup per product.
CREATE INDEX IF NOT EXISTS input_department_catalog_cover
ON input_price(department,observed_on DESC,id)
INCLUDE(price,name,category,presentation,document_id,source_locator,brand,registration,product_line);
