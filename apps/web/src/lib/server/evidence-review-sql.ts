/** Review counts follow committed extraction, independent of URL aliases. */
export const EVIDENCE_REVIEW_COUNT_SQL = `WITH latest_input AS (
  SELECT processor_version FROM ingestion_checkpoint
  WHERE document_id=$1 AND step='inputs-pdf:published'
    AND processor_version ~ '^inputs-pdf-v[0-9]+$'
  ORDER BY substring(processor_version from '([0-9]+)$')::numeric DESC LIMIT 1
)
SELECT ((SELECT count(DISTINCT r.source_locator)
  FROM official_source_review r WHERE r.document_id=$1
  AND NOT EXISTS(SELECT 1 FROM official_price_quote q
    WHERE q.document_id=r.document_id AND q.source_locator=r.source_locator AND q.parsed_at>r.created_at)
  AND NOT EXISTS(SELECT 1 FROM historical_price h
    WHERE h.document_id=r.document_id AND h.source_locator=r.source_locator))
  + (SELECT count(*) FROM historical_price h JOIN latest_input v
      ON h.details->>'parser_version'=v.processor_version
    WHERE h.document_id=$1 AND h.series='dane-inputs-pdf-unresolved'))::int AS count,
  (SELECT min(reason) FROM official_source_review
    WHERE document_id=$1 AND source_locator='advisory source identity') AS identity_note`;
