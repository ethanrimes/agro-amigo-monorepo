-- Keep the small latest-input projection usable while a resumable input
-- publication changes raw rows. The statement trigger records every affected
-- identity in the same transaction as its epoch advance. Readers overlay only
-- those IDs; withdrawn documents and aliases are still checked live.
CREATE TABLE IF NOT EXISTS input_latest_projection_delta (
  scope text NOT NULL CHECK (scope IN ('department','municipality')),
  id text NOT NULL,
  changed_epoch bigint NOT NULL,
  PRIMARY KEY(scope,id)
);
CREATE INDEX IF NOT EXISTS input_latest_projection_delta_epoch
  ON input_latest_projection_delta(scope,changed_epoch,id);
ALTER TABLE input_latest_projection_state
  ADD COLUMN IF NOT EXISTS delta_complete boolean NOT NULL DEFAULT false;
-- On first installation only a projection already at this epoch/day needs no
-- historical delta. A stale projection stays on the exact raw fallback until
-- the worker's next successful refresh establishes a complete baseline.
UPDATE input_latest_projection_state
SET delta_complete=true
WHERE source_epoch=projection_epoch
  AND asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date;

CREATE OR REPLACE FUNCTION input_latest_projection_changed() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE changed boolean;
DECLARE next_epoch bigint;
BEGIN
  IF TG_OP = 'INSERT' THEN
    SELECT EXISTS (SELECT 1 FROM new_rows) INTO changed;
  ELSIF TG_OP = 'DELETE' THEN
    SELECT EXISTS (SELECT 1 FROM old_rows) INTO changed;
  ELSIF TG_ARGV[0] = 'department' THEN
    SELECT EXISTS (
      SELECT 1 FROM old_rows o FULL JOIN new_rows n
        ON o.id=n.id AND o.department=n.department
          AND o.observed_on=n.observed_on
      WHERE o IS DISTINCT FROM n
    ) INTO changed;
  ELSE
    SELECT EXISTS (
      SELECT 1 FROM old_rows o FULL JOIN new_rows n
        ON o.id=n.id AND o.department=n.department
          AND o.observed_on=n.observed_on
          AND o.municipality=n.municipality
      WHERE o IS DISTINCT FROM n
    ) INTO changed;
  END IF;
  IF NOT changed THEN RETURN NULL; END IF;

  UPDATE public.input_latest_projection_state
    SET source_epoch=source_epoch+1 WHERE scope=TG_ARGV[0]
    RETURNING source_epoch INTO next_epoch;
  IF TG_OP = 'INSERT' THEN
    INSERT INTO public.input_latest_projection_delta(scope,id,changed_epoch)
      SELECT DISTINCT TG_ARGV[0],id,next_epoch FROM new_rows WHERE true
      ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=greatest(
        input_latest_projection_delta.changed_epoch,excluded.changed_epoch);
  ELSIF TG_OP = 'DELETE' THEN
    INSERT INTO public.input_latest_projection_delta(scope,id,changed_epoch)
      SELECT DISTINCT TG_ARGV[0],id,next_epoch FROM old_rows WHERE true
      ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=greatest(
        input_latest_projection_delta.changed_epoch,excluded.changed_epoch);
  ELSE
    INSERT INTO public.input_latest_projection_delta(scope,id,changed_epoch)
      SELECT DISTINCT TG_ARGV[0],id,next_epoch FROM (
        SELECT id FROM old_rows UNION SELECT id FROM new_rows
      ) affected WHERE true
      ON CONFLICT(scope,id) DO UPDATE SET changed_epoch=greatest(
        input_latest_projection_delta.changed_epoch,excluded.changed_epoch);
  END IF;
  RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION input_latest_projection_truncated() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE changed boolean;
BEGIN
  EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s LIMIT 1)',TG_RELID::regclass)
  INTO changed;
  IF changed THEN
    UPDATE public.input_latest_projection_state
      SET source_epoch=source_epoch+1,delta_complete=false
      WHERE scope=TG_ARGV[0];
  END IF;
  RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION refresh_input_latest_projection(requested_scope text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE captured_epoch bigint;
DECLARE captured_day date;
DECLARE updated_rows integer;
DECLARE populated boolean;
BEGIN
  IF requested_scope NOT IN ('department','municipality') THEN
    RAISE EXCEPTION 'Invalid input projection scope';
  END IF;
  SELECT source_epoch INTO captured_epoch
  FROM public.input_latest_projection_state WHERE scope=requested_scope;
  captured_day := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date;
  IF requested_scope='department' THEN
    SELECT relispopulated INTO populated FROM pg_catalog.pg_class
      WHERE oid='public.input_department_latest_raw'::regclass;
    IF populated THEN
      REFRESH MATERIALIZED VIEW CONCURRENTLY public.input_department_latest_raw;
    ELSE
      REFRESH MATERIALIZED VIEW public.input_department_latest_raw;
    END IF;
  ELSE
    SELECT relispopulated INTO populated FROM pg_catalog.pg_class
      WHERE oid='public.input_municipal_latest_raw'::regclass;
    IF populated THEN
      REFRESH MATERIALIZED VIEW CONCURRENTLY public.input_municipal_latest_raw;
    ELSE
      REFRESH MATERIALIZED VIEW public.input_municipal_latest_raw;
    END IF;
  END IF;
  UPDATE public.input_latest_projection_state
    SET projection_epoch=captured_epoch,asof_bogota=captured_day,
      delta_complete=true
  WHERE scope=requested_scope AND source_epoch=captured_epoch;
  GET DIAGNOSTICS updated_rows = ROW_COUNT;
  IF updated_rows=1 THEN
    DELETE FROM public.input_latest_projection_delta
    WHERE scope=requested_scope AND changed_epoch<=captured_epoch;
  END IF;
  RETURN updated_rows=1;
END $$;

GRANT SELECT ON input_latest_projection_delta TO agro_reader;
REVOKE ALL ON FUNCTION input_latest_projection_changed() FROM PUBLIC;
REVOKE ALL ON FUNCTION input_latest_projection_truncated() FROM PUBLIC;
REVOKE ALL ON FUNCTION refresh_input_latest_projection(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION refresh_input_latest_projection(text) TO agro_ingestor;
