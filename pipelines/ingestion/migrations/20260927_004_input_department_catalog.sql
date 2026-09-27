-- Department-filtered catalogs should scan that department's recent rows only.
-- Existing deployments can build this CONCURRENTLY before applying migrations.
CREATE INDEX IF NOT EXISTS input_department_recent_catalog
ON input_price(department,observed_on,id);
