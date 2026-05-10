-- Add the unique constraints needed for idempotent ingestion.
--
-- Background:
--   * populate-dimensions used to INSERT...SELECT into price_observations without
--     ON CONFLICT, so every run appended duplicate rows. We now use
--     ON CONFLICT (processed_price_id), which requires this unique index.
--   * The insumos parser now creates dim_city rows on the fly via
--     INSERT ... ON CONFLICT (canonical_name); divipola_code lookups are still done
--     with a SELECT first, but the unique index on divipola_code makes that lookup
--     fast and lets us treat the column as the actual external key.
--
-- The dedupe is run separately (scripts/dedupe_price_observations.py) before this
-- migration is applied; the CREATE UNIQUE INDEX will fail loudly otherwise.

CREATE UNIQUE INDEX IF NOT EXISTS price_observations_processed_price_id_uq
    ON price_observations (processed_price_id);

CREATE UNIQUE INDEX IF NOT EXISTS dim_city_divipola_code_uq
    ON dim_city (divipola_code);
