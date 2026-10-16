-- Derived-cache scheduling only. Originals, immutable quotes/reviews, payloads,
-- and the published winner query are unchanged. A newly invalidated old card
-- must not jump ahead of a key that was already waiting for refresh.
ALTER TABLE official_catalog_current
  ADD COLUMN IF NOT EXISTS dirty_since timestamptz;

-- Preserve the previous FIFO order at rollout. NULL refreshed_at represented
-- never-refreshed keys and sorted first; -infinity retains that priority.
UPDATE official_catalog_current
SET dirty_since=coalesce(refreshed_at,'-infinity'::timestamptz)
WHERE dirty AND dirty_since IS NULL;
UPDATE official_catalog_current SET dirty_since=NULL
WHERE NOT dirty AND dirty_since IS NOT NULL;

CREATE OR REPLACE FUNCTION stamp_official_catalog_dirty_since()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT NEW.dirty THEN
    NEW.dirty_since := NULL;
  ELSIF TG_OP='INSERT' THEN
    NEW.dirty_since := coalesce(NEW.dirty_since,clock_timestamp());
  ELSIF OLD.dirty THEN
    -- A repeat invalidation while still dirty keeps its place in the queue.
    NEW.dirty_since := coalesce(OLD.dirty_since,clock_timestamp());
  ELSE
    -- The row lock has been acquired; stamp after a concurrent refresh wait.
    NEW.dirty_since := clock_timestamp();
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS official_catalog_dirty_fifo_stamp ON official_catalog_current;
CREATE TRIGGER official_catalog_dirty_fifo_stamp
BEFORE INSERT OR UPDATE ON official_catalog_current
FOR EACH ROW EXECUTE FUNCTION stamp_official_catalog_dirty_since();

CREATE INDEX IF NOT EXISTS official_catalog_dirty_fifo
ON official_catalog_current(dirty_since,quote_key) WHERE dirty;
