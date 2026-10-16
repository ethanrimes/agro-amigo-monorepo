/** Search original metadata, retained filename dates and published city report dates. */
import { SOURCE_DOCUMENT_SUBJECT_SQL, SOURCE_DOCUMENT_DISPLAY_TITLE_SQL,
  SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL } from "./source-document-subjects";
import { sqlSearchFold } from "./sql-search-fold";
import { REVIEWED_CITY_MARKET_JOIN_SQL } from "./reviewed-city-source-markets";
import { AGRICULTURAL_SOURCE_SCOPE_SQL } from "./source-document-scope";
export const ARCHIVE_SEARCH_LIMIT = 40;
export type ArchiveCursor = { at: string; id: string };

/** Preserve PostgreSQL microseconds so copies archived together cannot be skipped. */
export function archiveSearchCursor(raw: string | null): ArchiveCursor | null {
  if (!raw || raw.length > 320 || !/^[A-Za-z0-9_-]+$/.test(raw)) return null;
  try {
    const cursor = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
    if (typeof cursor.at !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(cursor.at) ||
      !Number.isFinite(Date.parse(cursor.at)) ||
      new Date(cursor.at).toISOString().slice(0, 19) !== cursor.at.slice(0, 19) ||
      typeof cursor.id !== "string" || !/^[a-f0-9]{64}$/.test(cursor.id)) return null;
    return { at: cursor.at, id: cursor.id };
  } catch { return null; }
}

export function archiveNextCursor(row: { id: string; archive_sort_time: string }): string {
  return Buffer.from(JSON.stringify({ at: row.archive_sort_time, id: row.id })).toString("base64url");
}

export function archiveSearchTerms(raw: string): string[] | null {
  if (raw.length > 120 || /[\u0000-\u001f\u007f]/.test(raw)) return null;
  const query = raw.trim().replace(/\s+/g, " ");
  if (query.length < 3 || query.length > 100)
    return null;
  if (/^[a-f0-9]{64}$/i.test(query)) return [query.toLowerCase()];
  const terms = query.normalize("NFD").replace(/\p{M}/gu, "").split(" ")
    .filter((term) => !/^(y|e|o|u|de|del|el|la|los|las)$/i.test(term));
  if (!terms.length || terms.length > 5) return null;
  return terms.map((term) => `%${term.replace(/[\\%_]/g, "\\$&")}%`);
}

const SEARCH_TEXT = sqlSearchFold(`(${SOURCE_DOCUMENT_DISPLAY_TITLE_SQL}) || ' ' || d.title || ' ' || d.publisher || ' ' || d.reference_period || ' ' || COALESCE((${SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL}),'') || ' ' || COALESCE(d.metadata->>'original_filename','') || ' ' || (${SOURCE_DOCUMENT_SUBJECT_SQL}) || ' ' || COALESCE(reviewed_market.market_name,'')`);

function calendarSearchDay(term: string): { iso: string; filenamePattern: string; isoTerm: boolean } | null {
  const iso = /^%(\d{4})-(\d{2})-(\d{2})%$/.exec(term);
  const filename = /^%(\d{1,2})([-/])(\d{1,2})\2(\d{4})%$/.exec(term);
  if (!iso && !filename) return null;
  const year = Number((iso || filename)![iso ? 1 : 4]);
  const month = Number((iso || filename)![iso ? 2 : 3]);
  const day = Number((iso || filename)![iso ? 3 : 1]);
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const value = `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const date = new Date(`${value}T12:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) return null;
  // A filename is searchable evidence, never a claim that the PDF published a
  // price on this day. Digit boundaries keep 5-1 distinct from 15-1.
  const filenameDay = day < 10 ? `0?${day}` : String(day);
  const filenameMonth = month < 10 ? `0?${month}` : String(month);
  const filenameYear = String(year).padStart(4, "0");
  return { iso: value,
    filenamePattern: `(^|[^0-9])(${filenameDay}-${filenameMonth}-${filenameYear}|${value})([^0-9]|$)`,
    isoTerm: Boolean(iso) };
}

export function archiveSearchSql(terms: string[], cursor = false): string {
  const dateTerms = terms.flatMap((term, index) => {
    const date = calendarSearchDay(term);
    return date ? [{ index, parameter: `$${index + 1}`, ...date }] : [];
  });
  // The authoritative publication gate is evaluated once per date term.
  // Materialization prevents a document-by-document lookup while preserving
  // one statement snapshot and the existing metadata search arm.
  const dateSet = dateTerms.length ? `WITH ${dateTerms.map(({ index, parameter, iso, isoTerm }) =>
    `published_day_${index + 1} AS MATERIALIZED (
      SELECT DISTINCT p.document_id FROM published_regional_price p
      WHERE p.observed_on=${isoTerm ? `substring(${parameter}::text FROM 2 FOR 10)::date` : `date '${iso}'`}
    )`).join(',\n')}\n` : '';
  const filters = terms.length === 1 && /^[a-f0-9]{64}$/.test(terms[0])
    ? ["d.id=$1"]
    : terms.map((term, index) => {
      const parameter = `$${index + 1}`;
      const metadata = `${SEARCH_TEXT} ILIKE ${parameter} ESCAPE '\\'`;
      const date = calendarSearchDay(term);
      if (!date) return metadata;
      // City member filenames may have D-M-YYYY while the user enters ISO or
      // zero-padded or slash-separated DMY. Keep the date match token-bounded: a plain substring
      // search for 5-1 would also return 15-1 from a title derived from the
      // filename. Other original kinds retain their existing metadata search.
      return `((${metadata} AND NOT (d.media_type='application/pdf'
        AND d.metadata->>'ingestion_kind' IS NOT DISTINCT FROM 'city-pdf')) OR (d.media_type='application/pdf'
        AND d.metadata->>'ingestion_kind'='city-pdf'
        AND (d.id IN (SELECT document_id FROM published_day_${index + 1})
          OR COALESCE(d.metadata->>'original_filename','') ~* '${date.filenamePattern}')))`;
    });
  if (cursor) filters.push(`(d.retrieved_at < $${terms.length + 1}::timestamptz OR
    (d.retrieved_at = $${terms.length + 1}::timestamptz AND d.id > $${terms.length + 2}))`);
  return `${dateSet}SELECT d.id,${SOURCE_DOCUMENT_DISPLAY_TITLE_SQL} AS title,d.title AS archived_title,
    d.publisher,d.reference_period,d.kind,d.media_type,d.retrieved_at,
    to_char(d.retrieved_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS archive_sort_time,
    ${SOURCE_DOCUMENT_DISPLAY_FILENAME_SQL} AS filename,
    d.metadata->>'original_filename' AS archived_filename,${SOURCE_DOCUMENT_SUBJECT_SQL} AS subject,
    reviewed_market.market_name AS verified_market
  FROM source_document d
  ${REVIEWED_CITY_MARKET_JOIN_SQL}
  WHERE d.kind='original'
    AND ${AGRICULTURAL_SOURCE_SCOPE_SQL}
    AND (d.media_type IN ('application/pdf','application/zip','application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      OR (d.media_type='application/json' AND d.publisher='DANE'
        AND d.metadata->>'ingestion_kind'='dane-daily-query'
        AND d.source_url LIKE 'https://apps.dane.gov.co/pentaho/%'
        AND d.metadata->>'original_filename' ~ '^sipsa-[0-9]{4}-[0-9]{2}-[0-9]{2}-daily-prices[.]json$'))
    AND ${filters.join(" AND ")}
  ORDER BY d.retrieved_at DESC,d.id
  LIMIT ${ARCHIVE_SEARCH_LIMIT + 1}`;
}
