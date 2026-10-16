-- 001 was reapplied during schema initialization and marked already verified
-- monthly-pdf-v4 assets as review. Restore only that exact legacy review error
-- when the immutable v4 monetary rows and complete native page checkpoint agree.
UPDATE ingestion_asset a SET status='complete',error=NULL
WHERE a.kind='monthly-pdf'
 AND a.status='review'
 AND a.processor_version='monthly-pdf-v4'
 AND a.records>0
 AND a.error='Legacy monthly PDF price grids require table-local monetary verification; originals and prior parser rows retained'
 AND a.document_id IS NOT NULL
 AND a.records=(
   SELECT count(*) FROM historical_price h
   WHERE h.document_id=a.document_id
    AND h.series='dane-monthly-summary'
    AND h.details->>'parser_version'='monthly-pdf-v4'
 )
 AND EXISTS(
   SELECT 1 FROM source_pdf_page p
   WHERE p.document_id=a.document_id
    AND p.extraction_version='pdf-text-tables-v1'
   GROUP BY p.document_id
   HAVING min(p.page)=1 AND count(*)=max(p.page)
 );
