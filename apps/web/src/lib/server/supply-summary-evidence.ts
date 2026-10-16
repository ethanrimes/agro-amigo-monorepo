/** A source summary must never replace records selected by a price/crop filter. */
export function showsSupplySummaryRecords(filters: URLSearchParams): boolean {
  const viewerControls = new Set(["page", "sheet", "row", "zoom", "locator"]);
  for (const [key, value] of filters) {
    if (value && !viewerControls.has(key)) return false;
  }
  const locator = filters.get("locator");
  return !locator || /^Abastecimiento!row \d+,col \d+; supply-daily-summary-v\d+$/.test(locator)
    || /^PDF page \d+, row y\d+\.\d{2}, column [1-8]; supply-daily-pdf-summary-v\d+$/.test(locator)
    || /^(?:[123]!row \d+,col \d+|PDF page \d+, row y\d+\.\d{2}, column [123]|PDF page \d+, OCR table \d+, row \d+, column [234](?:; printed-row-v2)?); supply-period-summary(?:-workbook)?-v\d+$/.test(locator);
}

// One immutable source can keep rows from several parser revisions. The asset's
// durable record count identifies the complete revision; older source cells
// remain addressable through their exact locators without inflating the
// ordinary source summary or replacing a partial parse with a newer partial.
export const SUPPLY_PERIOD_CANONICAL_VERSION_SQL = `
WITH versions AS (
  SELECT (regexp_match(source_locator,
    'supply-period-summary(?:-workbook)?-v([0-9]+)$'))[1]::int version,
    count(*)::int cells
  FROM input_reference_row
  WHERE document_id=$1 AND kind='supply-period-summary'
  GROUP BY 1
), asset AS (
  SELECT records,processor_version,status FROM ingestion_asset
  WHERE document_id=$1 AND kind IN ('supply-reference','supply-reference-pdf')
  ORDER BY CASE WHEN status='complete' THEN 0 ELSE 1 END,
    checked_at DESC NULLS LAST LIMIT 1
)
SELECT v.version FROM versions v CROSS JOIN asset a
WHERE v.version IS NOT NULL AND v.cells=a.records
  AND (v.version < 8 OR a.status='complete')
ORDER BY CASE WHEN a.processor_version ~
  ('(^|:)supply-period-summary-v' || v.version::text || '$') THEN 0 ELSE 1 END,
  v.version ASC LIMIT 1`;

export const SUPPLY_PERIOD_SUMMARY_SQL = `
SELECT count(*) FILTER(WHERE details->>'unit'='t')::int tonnes,
 count(*) FILTER(WHERE details->>'unit'='percentage_points')::int percentages,
 count(*)::int cells,min(details->>'period_start') first_day,
 max(details->>'period_end') last_day,min(details->>'sheet') sheet,
 min((details->>'source_page')::int) page,min(details->>'frequency') frequency
FROM input_reference_row
WHERE document_id=$1 AND kind='supply-period-summary'
  AND source_locator ~ ('supply-period-summary(?:-workbook)?-v' || $2::text || '$')`;

export const SUPPLY_PERIOD_ROWS_SQL = `
SELECT kind,observed_on,name,category,source_locator,
 details->>'unit' unit,details->'value' value,
 details->>'aggregation_level' aggregation_level,details
FROM input_reference_row
WHERE document_id=$1 AND kind='supply-period-summary'
  AND ($2='' OR source_locator=$2)
  AND ($2<>'' OR source_locator ~ ('supply-period-summary(?:-workbook)?-v' || $3::text || '$'))
ORDER BY observed_on DESC,source_locator LIMIT 100`;
