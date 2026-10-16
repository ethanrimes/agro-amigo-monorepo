-- A narrow visibility bridge for cooperative ingestion pacing. The ingestor
-- must not receive pg_read_all_stats, which would expose other SQL activity.
CREATE OR REPLACE FUNCTION public.agro_readers_active()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog AS $$
  SELECT EXISTS (
    SELECT 1 FROM pg_catalog.pg_stat_activity
    WHERE usename = 'agro_reader' AND state = 'active'
  );
$$;
DO $$ BEGIN
  IF NOT pg_catalog.pg_has_role(
    (SELECT pg_catalog.pg_get_userbyid(proowner) FROM pg_catalog.pg_proc
     WHERE oid='public.agro_readers_active()'::pg_catalog.regprocedure),
    'pg_read_all_stats','member'
  ) THEN
    RAISE EXCEPTION 'agro_readers_active owner cannot observe reader state';
  END IF;
END $$;
REVOKE ALL ON FUNCTION public.agro_readers_active() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.agro_readers_active() TO agro_ingestor;
