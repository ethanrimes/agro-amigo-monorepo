-- Retained originals and archive membership are append-only. The worker may
-- insert new revisions, but has no need to rewrite either immutable table.
-- Existing history protection triggers remain unchanged.
DO $migration$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agro_ingestor') THEN
    REVOKE UPDATE ON public.source_document, public.source_archive_member
      FROM agro_ingestor;
  END IF;
END
$migration$;
