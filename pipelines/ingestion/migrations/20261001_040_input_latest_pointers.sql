-- Bounded catalog/comparison reads retain one raw winner per exact location.
-- The published_input_* views remain authoritative for withdrawn revisions and
-- identity aliases; these pointers are never treated as publication decisions.
CREATE TABLE IF NOT EXISTS input_latest_projection_state (
  scope text PRIMARY KEY CHECK (scope IN ('department','municipality')),
  source_epoch bigint NOT NULL DEFAULT 0,
  projection_epoch bigint NOT NULL DEFAULT -1,
  asof_bogota date
);
INSERT INTO input_latest_projection_state(scope) VALUES ('department'),('municipality')
ON CONFLICT (scope) DO NOTHING;

CREATE MATERIALIZED VIEW IF NOT EXISTS input_department_latest_raw AS
SELECT DISTINCT ON (id,department) id,department,observed_on,price
FROM input_price
WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
ORDER BY id,department,observed_on DESC,price
WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS input_department_latest_raw_location
ON input_department_latest_raw(id,department);
CREATE INDEX IF NOT EXISTS input_department_latest_raw_catalog
ON input_department_latest_raw(id,observed_on DESC,price,department);
CREATE INDEX IF NOT EXISTS input_department_latest_raw_named
ON input_department_latest_raw(department,id,observed_on DESC,price);

CREATE MATERIALIZED VIEW IF NOT EXISTS input_municipal_latest_raw AS
SELECT DISTINCT ON (id,department,municipality) id,department,municipality,observed_on,price
FROM input_municipal_price
WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
ORDER BY id,department,municipality,observed_on DESC,price
WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS input_municipal_latest_raw_location
ON input_municipal_latest_raw(id,department,municipality);
CREATE INDEX IF NOT EXISTS input_municipal_latest_raw_catalog
ON input_municipal_latest_raw(id,observed_on DESC,price,department,municipality);
CREATE INDEX IF NOT EXISTS input_municipal_latest_raw_named
ON input_municipal_latest_raw(department,id,observed_on DESC,price,municipality);
CREATE INDEX IF NOT EXISTS input_municipal_latest_raw_place
ON input_municipal_latest_raw(department,municipality,id,observed_on DESC,price);

-- Transition tables keep the epoch unchanged for empty or equal-value UPSERTs.
CREATE OR REPLACE FUNCTION input_latest_projection_changed() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE changed boolean;
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
  IF changed THEN
    UPDATE public.input_latest_projection_state SET source_epoch=source_epoch+1
    WHERE scope=TG_ARGV[0];
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
    UPDATE public.input_latest_projection_state SET source_epoch=source_epoch+1
    WHERE scope=TG_ARGV[0];
  END IF;
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS input_price_projection_insert ON input_price;
CREATE TRIGGER input_price_projection_insert AFTER INSERT ON input_price
REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('department');
DROP TRIGGER IF EXISTS input_price_projection_update ON input_price;
CREATE TRIGGER input_price_projection_update AFTER UPDATE ON input_price
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('department');
DROP TRIGGER IF EXISTS input_price_projection_delete ON input_price;
CREATE TRIGGER input_price_projection_delete AFTER DELETE ON input_price
REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('department');
DROP TRIGGER IF EXISTS input_price_projection_truncate ON input_price;
CREATE TRIGGER input_price_projection_truncate BEFORE TRUNCATE ON input_price
FOR EACH STATEMENT EXECUTE FUNCTION input_latest_projection_truncated('department');

DROP TRIGGER IF EXISTS input_municipal_projection_insert ON input_municipal_price;
CREATE TRIGGER input_municipal_projection_insert AFTER INSERT ON input_municipal_price
REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('municipality');
DROP TRIGGER IF EXISTS input_municipal_projection_update ON input_municipal_price;
CREATE TRIGGER input_municipal_projection_update AFTER UPDATE ON input_municipal_price
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('municipality');
DROP TRIGGER IF EXISTS input_municipal_projection_delete ON input_municipal_price;
CREATE TRIGGER input_municipal_projection_delete AFTER DELETE ON input_municipal_price
REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT
EXECUTE FUNCTION input_latest_projection_changed('municipality');
DROP TRIGGER IF EXISTS input_municipal_projection_truncate ON input_municipal_price;
CREATE TRIGGER input_municipal_projection_truncate BEFORE TRUNCATE ON input_municipal_price
FOR EACH STATEMENT EXECUTE FUNCTION input_latest_projection_truncated('municipality');

-- The worker calls this after a committed input batch. A concurrent insert or
-- update during refresh leaves the projection stale and forces the API's raw
-- path until a later refresh catches up.
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
    SET projection_epoch=captured_epoch,asof_bogota=captured_day
  WHERE scope=requested_scope AND source_epoch=captured_epoch;
  GET DIAGNOSTICS updated_rows = ROW_COUNT;
  RETURN updated_rows=1;
END $$;

GRANT SELECT ON input_department_latest_raw,input_municipal_latest_raw,
  input_latest_projection_state TO agro_reader;
GRANT SELECT ON input_latest_projection_state TO agro_ingestor;
REVOKE ALL ON FUNCTION input_latest_projection_changed() FROM PUBLIC;
REVOKE ALL ON FUNCTION input_latest_projection_truncated() FROM PUBLIC;
REVOKE ALL ON FUNCTION refresh_input_latest_projection(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION refresh_input_latest_projection(text) TO agro_ingestor;
