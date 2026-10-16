-- Additive, append-only attribution for exactly one source-backed local OCR review.
-- The sole page-2 Gemini reading is never represented as a second provider result.
CREATE TABLE IF NOT EXISTS city_corabastos_ocr_adjudication (
  document_id text NOT NULL REFERENCES source_document(id),
  policy_version text NOT NULL,
  archive_id text NOT NULL REFERENCES source_document(id),
  entry_name text NOT NULL,
  evidence_document_id text NOT NULL REFERENCES source_document(id),
  evidence_method text NOT NULL,
  image_ids text[] NOT NULL,
  provider_result_hashes jsonb NOT NULL,
  prior_tasks jsonb NOT NULL,
  full17_sha256 text NOT NULL,
  records integer NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(document_id,policy_version),
  CHECK (document_id='6e7e5c976a1c49579f36df98ce72d1df29b6b6c22cbac1c656abc7fd08afa89a'),
  CHECK (archive_id='c9ecd972491184f1bb1df8b8df556f1aa9ee6d70a0a28336dcdf8d07dad82cd7'),
  CHECK (entry_name='Bogotá, D.C., Corabastos-19-10-2023.pdf'),
  CHECK (policy_version='city-v8:corabastos-oct2023-ocr-whole-v1'),
  CHECK (evidence_method='local_retained_source_geometry_plus_five_cached_provider_readings'),
  CHECK (evidence_document_id='f46a80c16bef2b3071cb999f1fa9043c7fd873a5870af6316cdde9feee9f85a1'),
  CHECK (image_ids=ARRAY[
    '29af041419bf681bf76399ccd1ce925aede0496e7a2e63293f2575379aabf987',
    '2830361a9b5cf493605930e5d9d9f7f6480abb55e372334fc1113a815aa2447a',
    '1247ccf1f98cd3cae1c4a04f4f321eb9339cf44817209f3220e8ae7631de780a']::text[]),
  CHECK (provider_result_hashes=jsonb_build_object(
    'p1_r0','1c31bb1b4a5052d7cfae6b35fff0c20a532057d6835eb4313c34d9dad403996a',
    'p1_r1','7af3c4d9273bc37ab48f8282235676855332351dfed3c7e52651ae4c6bb6a6d5',
    'p2_r0','30b469baaf3da4b1faf65d50b258376d960a5f27157a73c5b048e163444514ac',
    'p2_r1',NULL,
    'p3_r0','878728b874d7c4625e742f1851f1a3cb6fea78e0a06ecd430789464dc6047201',
    'p3_r1','aa21a59a7607bbfc332a0fed2241f507460298dc3b81e367f13465bafccd1465')),
  CHECK (prior_tasks=jsonb_build_array(
    jsonb_build_object('page',1,'image_id',
      '29af041419bf681bf76399ccd1ce925aede0496e7a2e63293f2575379aabf987',
      'status','review','error',
      'Independent OCR readings disagree or contain uncertainty; not published as prices'),
    jsonb_build_object('page',2,'image_id',
      '2830361a9b5cf493605930e5d9d9f7f6480abb55e372334fc1113a815aa2447a',
      'status','review','error','OCR output was blocked or truncated'),
    jsonb_build_object('page',3,'image_id',
      '1247ccf1f98cd3cae1c4a04f4f321eb9339cf44817209f3220e8ae7631de780a',
      'status','review','error',
      'Independent OCR readings disagree or contain uncertainty; not published as prices'))),
  CHECK (full17_sha256='957497a12b7ce88172239ef7f38626961ff4b39a729293aa9de1cc5081fa3e3e'
    AND records=196)
);
DROP TRIGGER IF EXISTS immutable_history ON city_corabastos_ocr_adjudication;
CREATE TRIGGER immutable_history BEFORE UPDATE ON city_corabastos_ocr_adjudication
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
DROP TRIGGER IF EXISTS retain_history ON city_corabastos_ocr_adjudication;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON city_corabastos_ocr_adjudication
 FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT ON city_corabastos_ocr_adjudication TO agro_reader;
GRANT SELECT,INSERT ON city_corabastos_ocr_adjudication TO agro_ingestor;
