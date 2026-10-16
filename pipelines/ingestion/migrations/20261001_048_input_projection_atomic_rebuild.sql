-- Build a complete baseline beside the live projection. PostgreSQL's
-- CONCURRENTLY refresh performs an expensive whole-row duplicate comparison
-- on the payload-bearing view; the staging view needs no such comparison.
-- The old name remains readable until the final transactional metadata swap.
CREATE OR REPLACE FUNCTION refresh_input_latest_projection(requested_scope text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE captured_epoch bigint;
DECLARE captured_day date;
DECLARE live_name text;
DECLARE stage_name text;
DECLARE source_sql text;
DECLARE index_name text;
DECLARE final_index text;
BEGIN
  IF requested_scope NOT IN ('department','municipality') THEN
    RAISE EXCEPTION 'Invalid input projection scope';
  END IF;
  -- One builder per scope; a competing invocation obeys the caller's lock
  -- timeout and never removes another builder's staging relation.
  PERFORM pg_catalog.pg_advisory_xact_lock(47048,
    CASE requested_scope WHEN 'department' THEN 1 ELSE 2 END);
  SELECT source_epoch INTO captured_epoch
    FROM public.input_latest_projection_state WHERE scope=requested_scope;
  captured_day := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date;
  live_name := CASE requested_scope WHEN 'department'
    THEN 'input_department_latest_raw' ELSE 'input_municipal_latest_raw' END;
  stage_name := live_name || '_next';
  SELECT definition INTO source_sql FROM pg_catalog.pg_matviews
    WHERE schemaname='public' AND matviewname=live_name;
  IF source_sql IS NULL THEN RAISE EXCEPTION 'Missing input projection %',live_name; END IF;
  source_sql := pg_catalog.regexp_replace(source_sql,';[[:space:]]*$','');

  EXECUTE pg_catalog.format('DROP MATERIALIZED VIEW IF EXISTS public.%I',stage_name);
  EXECUTE pg_catalog.format('CREATE MATERIALIZED VIEW public.%I AS %s WITH NO DATA',
    stage_name,source_sql);
  EXECUTE pg_catalog.format('REFRESH MATERIALIZED VIEW public.%I',stage_name);
  IF requested_scope='department' THEN
    EXECUTE pg_catalog.format('CREATE UNIQUE INDEX %I ON public.%I(id,department)',
      stage_name||'_location',stage_name);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON public.%I(id,observed_on DESC,price,department)',
      stage_name||'_catalog',stage_name);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON public.%I(department,id,observed_on DESC,price)',
      stage_name||'_named',stage_name);
  ELSE
    EXECUTE pg_catalog.format('CREATE UNIQUE INDEX %I ON public.%I(id,department,municipality)',
      stage_name||'_location',stage_name);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON public.%I(id,observed_on DESC,price,department,municipality)',
      stage_name||'_catalog',stage_name);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON public.%I(department,id,observed_on DESC,price,municipality)',
      stage_name||'_named',stage_name);
    EXECUTE pg_catalog.format('CREATE INDEX %I ON public.%I(department,municipality,id,observed_on DESC,price)',
      stage_name||'_place',stage_name);
  END IF;
  EXECUTE pg_catalog.format('ANALYZE public.%I',stage_name);
  EXECUTE pg_catalog.format('GRANT SELECT ON public.%I TO agro_reader,agro_ingestor',stage_name);

  -- A concurrent writer advances source_epoch and records affected IDs in
  -- the same transaction. Keep those >captured_epoch deltas after the swap.
  -- The replacement may include some such rows; the overlay will seek their
  -- current raw winner again, which is correct in either snapshot ordering.
  EXECUTE pg_catalog.format('DROP MATERIALIZED VIEW public.%I',live_name);
  EXECUTE pg_catalog.format('ALTER MATERIALIZED VIEW public.%I RENAME TO %I',
    stage_name,live_name);
  FOREACH index_name IN ARRAY ARRAY['location','catalog','named','place'] LOOP
    IF index_name='place' AND requested_scope='department' THEN CONTINUE; END IF;
    final_index := live_name||'_'||index_name;
    EXECUTE pg_catalog.format('ALTER INDEX public.%I RENAME TO %I',
      stage_name||'_'||index_name,final_index);
  END LOOP;
  UPDATE public.input_latest_projection_state
    SET projection_epoch=captured_epoch,asof_bogota=captured_day,
      delta_complete=true
    WHERE scope=requested_scope;
  DELETE FROM public.input_latest_projection_delta
    WHERE scope=requested_scope AND changed_epoch<=captured_epoch;
  RETURN true;
END $$;

REVOKE ALL ON FUNCTION refresh_input_latest_projection(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION refresh_input_latest_projection(text) TO agro_ingestor;
