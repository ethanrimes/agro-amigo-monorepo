-- Publisher Retry-After applies to the hostname across URLs and worker runs.
-- Deferred assets keep their own state, source bytes, and checkpoints.
CREATE TABLE IF NOT EXISTS source_host_cooldown (
  host text PRIMARY KEY CHECK (length(host) BETWEEN 1 AND 253 AND host=lower(host)),
  retry_at timestamptz NOT NULL,
  checked_at timestamptz NOT NULL DEFAULT now(),
  response_status smallint NOT NULL DEFAULT 429 CHECK (response_status=429),
  retry_after_literal text
);

GRANT SELECT,INSERT,UPDATE ON source_host_cooldown TO agro_ingestor;
