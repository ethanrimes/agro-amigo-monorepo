/** Public municipal aptitude snapshots remain reachable independently of EVA crop coverage. */
import { SOURCE_DOCUMENT_SUBJECT_SQL, SOURCE_DOCUMENT_DISPLAY_TITLE_SQL,
  SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL } from "./source-document-subjects";
import { AGRICULTURAL_SOURCE_SCOPE_SQL } from "./source-document-scope";
export const SOURCE_LIBRARY_SQL = `WITH library AS (
  SELECT a.alias,d.id,${SOURCE_DOCUMENT_DISPLAY_TITLE_SQL} AS title,d.title AS archived_title,
    ${SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL} AS filename,
    d.metadata->>'original_filename' AS archived_filename,
    d.publisher,d.reference_period,d.kind,d.media_type,d.retrieved_at,
    false AS municipality_filter,${SOURCE_DOCUMENT_SUBJECT_SQL} AS subject
  FROM document_alias a JOIN source_document d ON d.id=a.document_id
  WHERE ${AGRICULTURAL_SOURCE_SCOPE_SQL} AND a.alias NOT LIKE 'price-%' AND NOT EXISTS (
    SELECT 1 FROM ingestion_asset i WHERE i.document_id=d.id AND i.status='review'
      AND i.kind='daily' AND a.alias='daily-' || i.observed_on::text || '-workbook'
  )
  UNION ALL
  SELECT NULL::text,d.id,${SOURCE_DOCUMENT_DISPLAY_TITLE_SQL} AS title,d.title AS archived_title,
    ${SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL} AS filename,
    d.metadata->>'original_filename' AS archived_filename,
    d.publisher,d.reference_period,d.kind,d.media_type,d.retrieved_at,
    true AS municipality_filter,${SOURCE_DOCUMENT_SUBJECT_SQL} AS subject
  FROM source_document d
  WHERE ${AGRICULTURAL_SOURCE_SCOPE_SQL} AND d.publisher='UPRA · SIPRA' AND d.kind='extract' AND d.media_type='application/json'
    AND EXISTS (SELECT 1 FROM crop_suitability s WHERE s.document_id=d.id)
) SELECT * FROM (
  SELECT DISTINCT ON (id) * FROM library
  ORDER BY id,municipality_filter DESC,alias NULLS LAST
) visible ORDER BY publisher,title`;
