import "server-only";

// Seek the next published day in the existing date-leading primary key.
// Scanning every quote just to build a date picker competes with price reads
// and ingestion; this still includes every retained published day.
export const DAILY_DATES_SQL = `WITH RECURSIVE dates(observed_on) AS (
  (SELECT observed_on FROM daily_price
   WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
   ORDER BY observed_on DESC LIMIT 1)
  UNION ALL
  SELECT previous.observed_on FROM dates d CROSS JOIN LATERAL (
    SELECT observed_on FROM daily_price WHERE observed_on<d.observed_on
    ORDER BY observed_on DESC LIMIT 1
  ) previous
)
SELECT observed_on::text AS date FROM dates ORDER BY observed_on DESC`;

// The bulletin alias alone does not prove that it contains a supply table.
// Resolve only retained, verified supply cells and their actual source page.
export const DAILY_SUPPLY_SOURCE_SQL = `SELECT d.id AS document_id,
  min(r.observed_on)::text AS first_day,max(r.observed_on)::text AS last_day,
  min(CASE WHEN (r.details->>'source_page') ~ '^[1-9][0-9]*$'
    THEN (r.details->>'source_page')::int END) AS source_page,
  min(nullif(r.details->>'sheet','')) AS sheet
FROM document_alias a JOIN source_document d ON d.id=a.document_id
JOIN input_reference_row r ON r.document_id=d.id AND r.kind='supply-daily-summary'
WHERE a.alias IN ('daily-'||$1::text||'-bulletin','daily-'||$1::text||'-workbook')
  AND $1::date<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  AND d.kind='original' AND CASE
    WHEN d.media_type='application/pdf' THEN CASE
      WHEN (r.details->>'source_page') ~ '^[1-9][0-9]*$'
        THEN (r.details->>'source_page')::int<=d.page_count ELSE false END
    WHEN d.media_type IN ('application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      THEN coalesce(length(r.details->>'sheet')>0,false)
    ELSE false END
GROUP BY d.id,d.media_type HAVING count(*)>0
ORDER BY CASE WHEN d.media_type='application/pdf' THEN 0 ELSE 1 END,d.id LIMIT 1`;
