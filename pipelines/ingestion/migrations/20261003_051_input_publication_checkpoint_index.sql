-- Eligibility probes must not scan a large document's unrelated resumable
-- checkpoints. Match the published input views' existing predicates exactly.
-- This index changes no publication rules or retained source/history rows.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ingestion_checkpoint_input_publication
 ON ingestion_checkpoint (
   document_id,
   (substring(processor_version from '([0-9]+)$')::numeric)
 )
 WHERE step='inputs-pdf:published'
   AND processor_version ~ '^inputs-pdf-v[0-9]+$';
