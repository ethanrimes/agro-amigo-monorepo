-- Guard reviewed older originals without hiding unrelated current catalog cards.
-- A source review can only withdraw versions at its exact locator. Keep a
-- previously refreshed current/previous card if EVERY revision there predates
-- the cached previous day. Otherwise mark dirty, as before.
CREATE OR REPLACE FUNCTION dirty_official_review_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE fresh_bogota_day date;
BEGIN
  PERFORM c.quote_key FROM official_catalog_current c
    JOIN (
      SELECT DISTINCT q.quote_key FROM new_official_reviews r
      JOIN official_price_quote q ON q.document_id=r.document_id
        AND q.source_locator=r.source_locator
    ) affected USING(quote_key)
    ORDER BY c.quote_key FOR UPDATE OF c;
  fresh_bogota_day := (clock_timestamp() AT TIME ZONE 'America/Bogota')::date;
  INSERT INTO official_catalog_current(quote_key)
  WITH affected AS MATERIALIZED (
    SELECT q.quote_key,max(q.observed_on) AS newest,
      count(*)=count(q.observed_on) AS all_dated
    FROM new_official_reviews r JOIN official_price_quote q
      ON q.document_id=r.document_id AND q.source_locator=r.source_locator
    GROUP BY q.quote_key
  )
  SELECT affected.quote_key FROM affected
  LEFT JOIN official_catalog_current c USING(quote_key)
  WHERE (
    c.quote_key IS NOT NULL AND NOT c.dirty
    AND c.version='official-catalog-v1' AND c.payload IS NOT NULL
    AND c.refreshed_at IS NOT NULL
    AND (c.refreshed_at AT TIME ZONE 'America/Bogota')::date=fresh_bogota_day
    AND c.winner_observed_on IS NOT NULL AND c.previous_observed_on IS NOT NULL
    AND c.previous_observed_on<c.winner_observed_on
    AND c.winner_observed_on<=fresh_bogota_day
    AND c.payload->>'observed_on'=to_char(c.winner_observed_on,'YYYY-MM-DD')
    AND affected.all_dated AND affected.newest<c.previous_observed_on
  ) IS NOT TRUE
  ORDER BY affected.quote_key
  ON CONFLICT(quote_key) DO UPDATE SET dirty=true
    WHERE NOT official_catalog_current.dirty;
  RETURN NULL;
END $$;

-- An asset review transition can suppress/re-enable every quote in its exact
-- original. Test all retained versions for each impacted key, not its filename
-- or a single parsed row. The trigger's original transition predicate remains.
CREATE OR REPLACE FUNCTION dirty_official_asset_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_document text; current_document text; fresh_bogota_day date;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NOT (OLD.status='review' OR NEW.status='review') OR
      (OLD.status,OLD.document_id,OLD.observed_on) IS NOT DISTINCT FROM
      (NEW.status,NEW.document_id,NEW.observed_on)
    THEN RETURN NULL; END IF;
  END IF;
  IF TG_OP<>'INSERT' AND OLD.status='review' THEN previous_document=OLD.document_id; END IF;
  IF TG_OP<>'DELETE' AND NEW.status='review' THEN current_document=NEW.document_id; END IF;
  IF previous_document IS NULL AND current_document IS NULL THEN RETURN NULL; END IF;

  PERFORM c.quote_key FROM official_catalog_current c
    JOIN (SELECT DISTINCT q.quote_key FROM official_price_quote q
      WHERE q.document_id IN (previous_document,current_document)) affected USING(quote_key)
    ORDER BY c.quote_key FOR UPDATE OF c;
  fresh_bogota_day := (clock_timestamp() AT TIME ZONE 'America/Bogota')::date;
  INSERT INTO official_catalog_current(quote_key)
  WITH affected AS MATERIALIZED (
    SELECT q.quote_key,max(q.observed_on) AS newest,
      count(*)=count(q.observed_on) AS all_dated
    FROM official_price_quote q
    WHERE q.document_id IN (previous_document,current_document)
    GROUP BY q.quote_key
  )
  SELECT affected.quote_key FROM affected
  LEFT JOIN official_catalog_current c USING(quote_key)
  WHERE (
    c.quote_key IS NOT NULL AND NOT c.dirty
    AND c.version='official-catalog-v1' AND c.payload IS NOT NULL
    AND c.refreshed_at IS NOT NULL
    AND (c.refreshed_at AT TIME ZONE 'America/Bogota')::date=fresh_bogota_day
    AND c.winner_observed_on IS NOT NULL AND c.previous_observed_on IS NOT NULL
    AND c.previous_observed_on<c.winner_observed_on
    AND c.winner_observed_on<=fresh_bogota_day
    AND c.payload->>'observed_on'=to_char(c.winner_observed_on,'YYYY-MM-DD')
    AND affected.all_dated AND affected.newest<c.previous_observed_on
  ) IS NOT TRUE
  ORDER BY affected.quote_key
  ON CONFLICT(quote_key) DO UPDATE SET dirty=true
    WHERE NOT official_catalog_current.dirty;
  RETURN NULL;
END $$;


-- Repair the same NULL-sensitive predicate in the existing quote-insert trigger.
CREATE OR REPLACE FUNCTION dirty_official_quote_catalog() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE fresh_bogota_day date;
BEGIN
  -- Serialize with refresh_keys' per-key row locks before checking the cached
  -- winner. Raw quote inserts and reviews remain append-only in all cases.
  PERFORM c.quote_key FROM official_catalog_current c
    JOIN (SELECT DISTINCT quote_key FROM new_official_quotes) n USING(quote_key)
    ORDER BY c.quote_key FOR UPDATE OF c;

  -- Capture one wall-current day AFTER any row-lock wait. A statement that
  -- began before midnight but waited through it must not treat yesterday's
  -- clean cache as fresh or suppress newly eligible future-dated quotes.
  fresh_bogota_day := (clock_timestamp() AT TIME ZONE 'America/Bogota')::date;

  INSERT INTO official_catalog_current(quote_key)
  WITH incoming AS MATERIALIZED (
    SELECT quote_key,max(observed_on) AS newest,
      count(*)=count(observed_on) AS all_dated
    FROM new_official_quotes GROUP BY quote_key
  ), superseding AS MATERIALIZED (
    SELECT DISTINCT n.quote_key FROM new_official_quotes n
      JOIN official_catalog_current incumbent ON incumbent.quote_key=n.quote_key
      JOIN official_price_quote prior_quote
        ON prior_quote.document_id=n.document_id AND prior_quote.source_locator=n.source_locator
    WHERE prior_quote.quote_key=n.quote_key
      AND prior_quote.observed_on>=incumbent.previous_observed_on
      -- Equal parsed_at is not a provable ordering: an equal-time correction
      -- at the same locator may change either cached winner.
      AND prior_quote.parsed_at<=n.parsed_at
  )
  SELECT incoming.quote_key FROM incoming
  LEFT JOIN official_catalog_current c USING(quote_key)
  LEFT JOIN superseding s USING(quote_key)
  WHERE (
    c.quote_key IS NOT NULL AND c.dirty=false
    AND c.version='official-catalog-v1' AND c.payload IS NOT NULL
    AND c.refreshed_at IS NOT NULL
    AND (c.refreshed_at AT TIME ZONE 'America/Bogota')::date = fresh_bogota_day
    AND c.winner_observed_on IS NOT NULL
    AND c.previous_observed_on IS NOT NULL
    AND c.previous_observed_on<c.winner_observed_on
    AND c.winner_observed_on<=fresh_bogota_day
    AND c.payload->>'observed_on'=to_char(c.winner_observed_on,'YYYY-MM-DD')
    AND incoming.all_dated AND incoming.newest<c.previous_observed_on
    -- A newer parse of the same locator could suppress a cached previous or
    -- latest quote even if its own observation date is older.
    AND s.quote_key IS NULL
  ) IS NOT TRUE
  ORDER BY incoming.quote_key
  ON CONFLICT(quote_key) DO UPDATE SET dirty=true
    WHERE NOT official_catalog_current.dirty;
  RETURN NULL;
END $$;
