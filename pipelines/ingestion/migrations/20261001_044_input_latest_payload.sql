-- The projection retains each exact raw winner's display and provenance.
-- Its small working set avoids thousands of seeks into historical raw tables
-- when national catalogs are requested during an unrelated publication write.
-- Re-running every migration must not invalidate a populated projection.
DO $$
DECLARE department_ready boolean;
DECLARE municipality_ready boolean;
BEGIN
  SELECT count(*)=8 INTO department_ready FROM pg_attribute
  WHERE attrelid='public.input_department_latest_raw'::regclass
    AND attnum>0 AND NOT attisdropped
    AND attname IN ('name','category','presentation','document_id',
      'source_locator','brand','registration','product_line');
  SELECT count(*)=8 INTO municipality_ready FROM pg_attribute
  WHERE attrelid='public.input_municipal_latest_raw'::regclass
    AND attnum>0 AND NOT attisdropped
    AND attname IN ('name','category','presentation','document_id',
      'source_locator','brand','registration','product_line');
  IF department_ready AND municipality_ready THEN RETURN; END IF;

  -- A stale marker makes the web use its exact raw fallback until both views
  -- have been populated by refresh_input_latest_projection().
  UPDATE input_latest_projection_state
    SET projection_epoch=-1,asof_bogota=NULL
  WHERE scope IN ('department','municipality');

  EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS public.input_department_latest_raw';
  EXECUTE $sql$CREATE MATERIALIZED VIEW public.input_department_latest_raw AS
    SELECT DISTINCT ON (id,department)
      id,department,observed_on,price,name,category,presentation,
      document_id,source_locator,brand,registration,product_line
    FROM public.input_price
    WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
    ORDER BY id,department,observed_on DESC,price WITH NO DATA$sql$;
  EXECUTE 'CREATE UNIQUE INDEX input_department_latest_raw_location ON public.input_department_latest_raw(id,department)';
  EXECUTE 'CREATE INDEX input_department_latest_raw_catalog ON public.input_department_latest_raw(id,observed_on DESC,price,department)';
  EXECUTE 'CREATE INDEX input_department_latest_raw_named ON public.input_department_latest_raw(department,id,observed_on DESC,price)';

  EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS public.input_municipal_latest_raw';
  EXECUTE $sql$CREATE MATERIALIZED VIEW public.input_municipal_latest_raw AS
    SELECT DISTINCT ON (id,department,municipality)
      id,department,municipality,observed_on,price,name,category,presentation,
      document_id,source_locator,brand,registration,product_line
    FROM public.input_municipal_price
    WHERE observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
    ORDER BY id,department,municipality,observed_on DESC,price WITH NO DATA$sql$;
  EXECUTE 'CREATE UNIQUE INDEX input_municipal_latest_raw_location ON public.input_municipal_latest_raw(id,department,municipality)';
  EXECUTE 'CREATE INDEX input_municipal_latest_raw_catalog ON public.input_municipal_latest_raw(id,observed_on DESC,price,department,municipality)';
  EXECUTE 'CREATE INDEX input_municipal_latest_raw_named ON public.input_municipal_latest_raw(department,id,observed_on DESC,price,municipality)';
  EXECUTE 'CREATE INDEX input_municipal_latest_raw_place ON public.input_municipal_latest_raw(department,municipality,id,observed_on DESC,price)';
END $$;

GRANT SELECT ON input_department_latest_raw,input_municipal_latest_raw TO agro_reader;
