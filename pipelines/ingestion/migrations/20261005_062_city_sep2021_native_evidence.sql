-- Append-only evidence for the source-bound September 1, 2021 city parser.
-- Parser and original hashes bind this evidence to the verified implementation.
CREATE TABLE IF NOT EXISTS public.city_native_sep2021_source_v44 (
 parent_document_id text NOT NULL REFERENCES public.source_document(id),
 document_id text NOT NULL REFERENCES public.source_document(id),
 entry_name text NOT NULL,
 parser_version text NOT NULL CHECK(parser_version='city-v8:sep2021-native-geometry-v44-private-v1'),
 parser_code_sha256 text NOT NULL CHECK(parser_code_sha256='eaeb7388da563434e3f3e0b394f3540fbf5d7cfab113112e88f57b03b4f58187'),
 oracle_sha256 text NOT NULL CHECK(oracle_sha256='f2153682db653b76753de301541607a8eedfb732c8c1b6df3a5b0f8a1589ca7e'),
 attested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,parser_version),
 UNIQUE(parent_document_id,entry_name,document_id,parser_version)
);
CREATE OR REPLACE FUNCTION public.check_city_native_sep2021_source_v44()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p public.source_document%ROWTYPE;
DECLARE c public.source_document%ROWTYPE;
BEGIN
 SELECT * INTO p FROM public.source_document WHERE id=NEW.parent_document_id;
 SELECT * INTO c FROM public.source_document WHERE id=NEW.document_id;
 IF NEW.parent_document_id <> 'cbd378bc2d1863439c9e0a806dcdaa5026ebdd9e920fbd9c63dc1473de589edf'
    OR (NEW.entry_name,NEW.document_id) NOT IN (VALUES
  ('BOGOTA 1 sep 21.pdf','f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93'),
  ('Barranquilla, Granabastos 01092021.pdf','f74ba57880a0a199d6926b8fb5652b652926d7d6ec7bfd17efea320186de1b2c'),
  ('Cartagena, Bazurto,, 1-sep-21.pdf','16381c4b870066c7f3f4aab8c0d732dc36187d3b088c68bb308a46ec6c33b463'),
  ('MONTERIA 1 sep 21.pdf','d0403c415af395c5bca852a4dd6977dfb1d5a784e040d579d58d0d9f97efdbee'),
  ('Medellín, Central Mayorista de Antioquia 01092021.pdf','36058d3e2ab35b83737c3379870dfc94cfc8f93798f6873101beb296f2bd68ad'),
  ('Pereira, Mercasa,, 1-sep-21.pdf','eaaafa06421b7ffba4828df57827e90987d9e889bbd854d5174b88831a32148f'),
  ('Popayán, 1-sep-21.pdf','301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66'),
  ('Santa Marta (Magdalena) 01092021.pdf','cc58e5ce38fa751138de088436ece59fb35610fc14eca39d1811f76d2009bd78'),
  ('Sincelejo, Nuevo Mercado 01092021.pdf','32c73fee19652051a882222b51178105fd36e65098c9004992bfb971ead116fc'),
  ('VILLAVICENCIO 1 sep 21.pdf','479bb6418ba84694e41bdf3b6249761127dd88fa1227b5e2dd3e3975430d5aa6'),
  ('Valledupar, Mercabastos,, 1-sep-21.pdf','80009b21f92c47bac30d7a8d181605682fa3404c43a96610d93305b4cfbf1058'))
    OR p.source_url IS DISTINCT FROM 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-01-09-2021.zip'
    OR p.kind IS DISTINCT FROM 'original'
    OR p.media_type IS DISTINCT FROM 'application/zip'
    OR p.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-zip'
    OR p.content IS NULL OR encode(sha256(p.content),'hex') IS DISTINCT FROM p.id
    OR c.kind IS DISTINCT FROM 'original'
    OR c.media_type IS DISTINCT FROM 'application/pdf'
    OR c.source_url IS DISTINCT FROM p.source_url
    OR c.metadata->>'ingestion_kind' IS DISTINCT FROM 'city-pdf'
    OR c.metadata->>'archive_entry' IS DISTINCT FROM NEW.entry_name
    OR NOT coalesce((c.metadata->'parents' @> to_jsonb(ARRAY[NEW.parent_document_id])),false)
    OR c.content IS NULL OR encode(sha256(c.content),'hex') IS DISTINCT FROM c.id
    OR NOT EXISTS (SELECT 1 FROM public.source_archive_member m
        WHERE m.archive_id=NEW.parent_document_id AND m.entry_name=NEW.entry_name
          AND m.document_id=NEW.document_id)
 THEN RAISE EXCEPTION 'Source-local native evidence original or lineage differs'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS source_v3_guard ON public.city_native_sep2021_source_v44;
CREATE TRIGGER source_v3_guard BEFORE INSERT ON public.city_native_sep2021_source_v44
 FOR EACH ROW EXECUTE FUNCTION public.check_city_native_sep2021_source_v44();
CREATE TABLE IF NOT EXISTS public.city_native_sep2021_evidence_v44 (
 document_id text NOT NULL,
 parent_document_id text NOT NULL,
 entry_name text NOT NULL,
 source_locator text NOT NULL,
 parser_version text NOT NULL,
 state text NOT NULL CHECK(state IN ('review','noquote','blank')),
 source_page integer NOT NULL CHECK(source_page>0),
 source_round smallint CHECK(source_round IN (1,2)),
 native_y numeric(9,2) NOT NULL,
 literal_cells jsonb NOT NULL CHECK(jsonb_typeof(literal_cells)='array' AND jsonb_array_length(literal_cells)=7),
 reason text NOT NULL CHECK(reason<>''),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(document_id,source_locator,parser_version),
 FOREIGN KEY(parent_document_id,entry_name,document_id,parser_version)
  REFERENCES public.city_native_sep2021_source_v44(parent_document_id,entry_name,document_id,parser_version),
 CHECK((state='blank' AND source_round IS NULL) OR
       (state IN ('review','noquote') AND source_round IS NOT NULL))
);
DROP TRIGGER IF EXISTS source_v3_retention ON public.city_native_sep2021_source_v44;
CREATE TRIGGER source_v3_retention BEFORE DELETE OR TRUNCATE ON public.city_native_sep2021_source_v44
 FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal();
DROP TRIGGER IF EXISTS source_v3_immutable ON public.city_native_sep2021_source_v44;
CREATE TRIGGER source_v3_immutable BEFORE UPDATE ON public.city_native_sep2021_source_v44
 FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal();
DROP TRIGGER IF EXISTS evidence_v3_retention ON public.city_native_sep2021_evidence_v44;
CREATE TRIGGER evidence_v3_retention BEFORE DELETE OR TRUNCATE ON public.city_native_sep2021_evidence_v44
 FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal();
DROP TRIGGER IF EXISTS evidence_v3_immutable ON public.city_native_sep2021_evidence_v44;
CREATE TRIGGER evidence_v3_immutable BEFORE UPDATE ON public.city_native_sep2021_evidence_v44
 FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_history_removal();
REVOKE ALL ON public.city_native_sep2021_source_v44,public.city_native_sep2021_evidence_v44 FROM PUBLIC;
GRANT SELECT ON public.city_native_sep2021_source_v44,public.city_native_sep2021_evidence_v44 TO agro_reader;
GRANT SELECT,INSERT ON public.city_native_sep2021_source_v44,public.city_native_sep2021_evidence_v44 TO agro_ingestor;
