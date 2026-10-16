-- Append-only source evidence for the verified Pereira native-text fallback.
-- One exact PDF inside a 13-member ZIP, not a whole-parent completion proof.
CREATE TABLE IF NOT EXISTS public.city_pereira_native_source_private (
 parent_document_id text NOT NULL REFERENCES public.source_document(id),
 document_id text NOT NULL REFERENCES public.source_document(id),
 entry_name text NOT NULL,
 parser_version text NOT NULL CHECK(parser_version='city-v8:pereira-20220106-native-category-private-v2'),
 parser_code_sha256 text NOT NULL CHECK(parser_code_sha256='7eaa363d8b79ca01070f20be7cab54eac02ba7fefea1177f2f5ad99085966a73'),
 oracle_sha256 text NOT NULL CHECK(oracle_sha256='3d33dc4e5f647fe893c338d2f328b77ac74f5d3d681fb2457adcbcf1f14a76b9'),
 attested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,parser_version),
 UNIQUE(parent_document_id,entry_name,document_id,parser_version)
);
CREATE OR REPLACE FUNCTION public.check_city_pereira_native_source_private()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p public.source_document%ROWTYPE;
DECLARE c public.source_document%ROWTYPE;
BEGIN
 SELECT * INTO p FROM public.source_document WHERE id=NEW.parent_document_id;
 SELECT * INTO c FROM public.source_document WHERE id=NEW.document_id;
 IF NEW.parent_document_id IS DISTINCT FROM '0f53db2e11ac41c7646bc011209c1029c6ca3f9eee590d0438b64d9c0010a08f'
    OR NEW.document_id IS DISTINCT FROM 'a309fbd8b620b034da2d2627618469c4b4716e0c00b1a83e4f0b98363dda4da4'
    OR NEW.entry_name IS DISTINCT FROM 'Pereira, Mercasa 6-1-2022.pdf'
    OR p.source_url IS DISTINCT FROM 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-06-01-2022.zip'
    OR p.kind IS DISTINCT FROM 'original' OR p.media_type IS DISTINCT FROM 'application/zip'
    OR p.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-zip'
    OR p.content IS NULL OR encode(sha256(p.content),'hex') IS DISTINCT FROM p.id
    OR c.source_url IS DISTINCT FROM p.source_url
    OR c.kind IS DISTINCT FROM 'original' OR c.media_type IS DISTINCT FROM 'application/pdf'
    OR c.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-pdf'
    OR c.metadata->>'archive_entry' IS DISTINCT FROM NEW.entry_name
    OR NOT coalesce((c.metadata->'parents' @> to_jsonb(ARRAY[NEW.parent_document_id])),false)
    OR c.content IS NULL OR encode(sha256(c.content),'hex') IS DISTINCT FROM c.id
    OR NOT EXISTS (SELECT 1 FROM public.source_archive_member m
        WHERE m.archive_id=NEW.parent_document_id AND m.entry_name=NEW.entry_name
          AND m.document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Pereira exact source/lineage proof differs'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS city_pereira_native_source_guard ON public.city_pereira_native_source_private;
CREATE TRIGGER city_pereira_native_source_guard BEFORE INSERT ON public.city_pereira_native_source_private
 FOR EACH ROW EXECUTE FUNCTION public.check_city_pereira_native_source_private();
DROP TRIGGER IF EXISTS city_pereira_native_source_no_update ON public.city_pereira_native_source_private;
CREATE TRIGGER city_pereira_native_source_no_update BEFORE UPDATE OR DELETE OR TRUNCATE ON public.city_pereira_native_source_private
 FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal();
REVOKE ALL ON public.city_pereira_native_source_private FROM PUBLIC;
GRANT SELECT ON public.city_pereira_native_source_private TO agro_reader;
GRANT SELECT,INSERT ON public.city_pereira_native_source_private TO agro_ingestor;
