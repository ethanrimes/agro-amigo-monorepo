/** Printed market names verified against exact retained city PDFs and native grids.
 * The review registry is also used by ingestion, but this is a read-only search
 * projection. An alias is visible only when the archived source identity and
 * provenance still match the reviewed member; original titles stay unchanged.
 */
import reviews from "../../../../../pipelines/ingestion/reviewed_city_dates.json";
import type { Evidence } from "../planning-types";

type ReviewedMember = {
  document_id: string;
  entry_name: string;
  printed_day: string;
  market_name: string;
};
type ReviewedArchive = {
  archive_id: string;
  archive_day: string;
  url: string;
  members: ReviewedMember[];
};

const quote = (value: string) => `'${value.replace(/'/g, "''")}'`;
const archives = reviews.archives as ReviewedArchive[];
const members = archives.flatMap((archive) => archive.members.map((member) => ({
  ...member,
  archive_id: archive.archive_id,
  archive_day: archive.archive_day,
  source_url: archive.url,
  filename: member.entry_name.split("/").at(-1) || "",
})));

if (reviews.format !== 1 || members.length > 100 ||
    new Set(members.map((member) => member.document_id)).size !== members.length ||
    members.some((member) => !/^[a-f0-9]{64}$/.test(member.document_id) ||
      !/^[a-f0-9]{64}$/.test(member.archive_id) ||
      !/^https:\/\/www\.dane\.gov\.co\/files\/.+[.]zip$/.test(member.source_url) ||
      !member.filename.endsWith(".pdf") || !member.market_name.trim() ||
      !/^\d{4}-\d{2}-\d{2}$/.test(member.printed_day) ||
      !/^\d{4}-\d{2}-\d{2}$/.test(member.archive_day))) {
  throw new Error("Invalid reviewed city source-market registry");
}

/** Fixed, bounded registry rows; every value is quoted from tracked review data. */
export const REVIEWED_CITY_MARKET_VALUES_SQL = members.map((member) =>
  `(${[
    member.document_id, member.archive_id, member.source_url,
    member.entry_name, member.filename, member.printed_day,
    member.market_name,
  ].map(quote).join(",")})`,
).join(",\n");

export const REVIEWED_CITY_MARKET_JOIN_SQL = `LEFT JOIN (VALUES
${REVIEWED_CITY_MARKET_VALUES_SQL}
) AS reviewed_market(document_id,archive_id,source_url,entry_name,filename,printed_day,market_name)
  ON reviewed_market.document_id=d.id
  AND d.kind='original' AND d.media_type='application/pdf' AND d.publisher='DANE'
  AND d.source_url=reviewed_market.source_url
  AND d.metadata->>'ingestion_kind'='city-pdf'
  AND d.metadata->>'original_filename'=reviewed_market.filename
  AND d.metadata->>'archive_entry'=reviewed_market.entry_name
  AND (d.metadata->'parents') ? reviewed_market.archive_id`;

/** Explain a reviewed printed date without renaming or rewriting the original. */
export function annotateReviewedCityDate(evidence: Evidence): void {
  if (evidence.kind !== "original" || evidence.media_type !== "application/pdf" ||
      evidence.publisher !== "DANE" || evidence.metadata.ingestion_kind !== "city-pdf" ||
      !Array.isArray(evidence.metadata.parents)) return;
  const member = members.find((item) => item.document_id === evidence.id &&
    item.source_url === evidence.source_url &&
    item.entry_name === evidence.metadata.archive_entry &&
    item.filename === evidence.metadata.original_filename &&
    (evidence.metadata.parents as unknown[]).includes(item.archive_id));
  if (!member || member.printed_day === member.archive_day) return;
  evidence.metadata.date_resolution_note =
    `Fecha impresa verificada de este informe por ciudad: ${member.printed_day}. ` +
    `El enlace del ZIP que lo contiene está fechado ${member.archive_day}; las fechas difieren. ` +
    `Los precios verificados de este informe corresponden a su fecha impresa, no a la del enlace. ` +
    `Conservamos los nombres y los archivos originales sin cambios.`;
}
