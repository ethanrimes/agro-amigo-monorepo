-- Original observations, source bytes, IDs and quote keys remain untouched.
CREATE TABLE IF NOT EXISTS published_label_correction (
 version text NOT NULL,entity text NOT NULL CHECK(entity='product'),
 entity_id text NOT NULL,field text NOT NULL CHECK(field IN ('name','category')),
 original_value text NOT NULL,normalized_value text NOT NULL,
 evidence jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(version,entity,entity_id,field,original_value),
 CHECK(original_value<>normalized_value)
);
CREATE TABLE IF NOT EXISTS published_label_scan (
 version text NOT NULL,entity text NOT NULL CHECK(entity='product'),
 after_id text NOT NULL DEFAULT '',scanned_at timestamptz,
 PRIMARY KEY(version,entity)
);
GRANT SELECT,INSERT ON published_label_correction TO agro_ingestor;
GRANT SELECT,INSERT,UPDATE ON published_label_scan TO agro_ingestor;
GRANT SELECT ON published_label_correction,published_label_scan TO agro_reader;
