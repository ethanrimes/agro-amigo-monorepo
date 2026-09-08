-- Independent, append-only evidence archive for public geospatial responses.
CREATE TABLE IF NOT EXISTS spatial_snapshot (
 id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{64}$'),
 cache_key text NOT NULL, title text NOT NULL, publisher text NOT NULL,
 source_url text NOT NULL, reference_period text NOT NULL,
 fetched_at timestamptz NOT NULL DEFAULT now(),
 content bytea NOT NULL CHECK(octet_length(content)<=12000000),
 records jsonb NOT NULL DEFAULT '[]', metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS spatial_snapshot_cache ON spatial_snapshot(cache_key,fetched_at DESC);
CREATE TABLE IF NOT EXISTS spatial_layer (
 id text PRIMARY KEY, definition jsonb NOT NULL,
 document_id text NOT NULL REFERENCES spatial_snapshot(id)
);
GRANT SELECT, INSERT ON spatial_snapshot TO agro_reader;
GRANT SELECT ON spatial_layer TO agro_reader;
REVOKE UPDATE, DELETE, TRUNCATE ON spatial_snapshot FROM agro_reader;
