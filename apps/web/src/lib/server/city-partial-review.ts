import type { Pool } from "pg";
import type { Evidence } from "../planning-types";

// The original omits Coco's numeric quantity. The reviewed native publisher
// can publish the other 35 rows without declaring the complete PDF resolved.
export const VALLEDUPAR_PARTIAL_SOURCE = {
  child: "908f8667c0f0880525062f7c812dcbfc433433aaa24d6ee9952c4a36dabcf337",
  parent: "3e3e990d35d925f102ecab674c674fd65135222117f0bbd268b2201f91a1be9a",
  url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-07-01-2022.zip",
  entry: "Valledupar, Mercabastos 7-1-2022.pdf",
  version: "city-v8:valledupar-jan2022-partial-v1",
  step: "city-member:b0202df54554c23641abc6e70c65a09dcb3c8ce5f7d50702911fb2b425f3952e",
} as const;

export const CITY_PARTIAL_REVIEW_SQL = `SELECT cp.step
  FROM source_archive_member member
  JOIN source_document parent ON parent.id=member.archive_id
  JOIN ingestion_asset asset ON asset.document_id=parent.id AND asset.url=parent.source_url
  JOIN ingestion_checkpoint priced ON priced.document_id=parent.id
    AND priced.processor_version=asset.processor_version AND priced.step=$6 AND priced.records=35
  JOIN ingestion_checkpoint cp ON cp.document_id=parent.id
    AND cp.processor_version=asset.processor_version AND cp.records=0
  WHERE member.document_id=$1 AND member.archive_id=$2 AND member.entry_name=$3
    AND parent.kind='original' AND parent.publisher='DANE'
    AND parent.media_type='application/zip' AND parent.source_url=$4
    AND parent.reference_period='2022-01-07'
    AND asset.kind='city-zip' AND asset.status='review' AND asset.records=1418
    AND asset.observed_on=DATE '2022-01-07' AND asset.processor_version=$5
    AND starts_with(cp.step,'review:')
    AND (SELECT count(*) FROM published_regional_price WHERE document_id=$1)=35
  ORDER BY cp.step LIMIT 33`;

export async function annotateCityPartialReview(db: Pick<Pool, "query">, source: Evidence): Promise<void> {
  const exact = VALLEDUPAR_PARTIAL_SOURCE;
  if (source.id !== exact.child || source.kind !== "original" || source.publisher !== "DANE" ||
      source.media_type !== "application/pdf" || source.source_url !== exact.url ||
      source.bytes !== 128456 || source.metadata.ingestion_kind !== "city-pdf" ||
      source.metadata.archive_entry !== exact.entry ||
      !Array.isArray(source.metadata.parents) || source.metadata.parents.length !== 1 ||
      source.metadata.parents[0] !== exact.parent) return;
  const rows = (await db.query<{ step: string }>(CITY_PARTIAL_REVIEW_SQL,
    [exact.child, exact.parent, exact.entry, exact.url, exact.version, exact.step])).rows;
  if (rows.length > 32) return;
  for (const { step } of rows) {
    if (typeof step !== "string" || step.length > 4096) continue;
    try {
      const review = JSON.parse(step.slice("review:".length));
      if (review.document_id === exact.child && review.filename === exact.entry &&
          review.error_type === "SourceQuantityOmitted") {
        source.metadata.city_partial_review_note = "Se publicaron 35 cotizaciones verificadas de este PDF. La fila de coco de la página 1 no se publica porque el documento no indica una cantidad numérica. Conservamos el archivo original completo para su consulta.";
        return;
      }
    } catch { /* An invalid checkpoint cannot supply a public source note. */ }
  }
}
