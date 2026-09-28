/** Immutable originals plus separately retained, auditable display annotations. */
export const SOURCE_DOCUMENT_EVIDENCE_SQL = `WITH selected AS (
  SELECT id,title,publisher,source_url,media_type,kind,reference_period,retrieved_at,
    page_count,octet_length(content) AS bytes,metadata
  FROM source_document
  WHERE id=$1 OR id=(SELECT document_id FROM document_alias WHERE alias=$1)
  LIMIT 1
)
SELECT d.id,d.title,d.publisher,d.source_url,d.media_type,d.kind,
  COALESCE(a.annotations->0->>'corrected_value',d.reference_period) AS reference_period,
  d.retrieved_at,d.page_count,d.bytes,
  d.metadata || CASE WHEN a.annotations IS NULL THEN '{}'::jsonb
    ELSE jsonb_build_object('original_reference_period',d.reference_period,
      'source_document_annotations',a.annotations) END AS metadata
FROM selected d LEFT JOIN LATERAL (
  SELECT jsonb_agg(jsonb_build_object(
    'annotation_id',annotation_id,'field',field,'original_value',original_value,
    'corrected_value',corrected_value,'reason',reason,'native_locators',native_locators,
    'created_at',created_at) ORDER BY annotation_id DESC) AS annotations
  FROM source_document_annotation
  WHERE document_id=d.id AND field='reference_period'
) a ON true`;
