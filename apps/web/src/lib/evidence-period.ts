import type { Evidence } from "./planning-types";
import { dateLabel } from "./market-types";

/** City evidence returns the complete verified PDF row set, unlike capped or
 * filtered workbook previews, which cannot establish the whole file's period. */
export function evidencePeriod(data: Evidence): string {
  if (data.metadata.ingestion_kind !== "city-pdf" || !data.records?.length)
    return data.reference_period;
  const days = data.records.map((row) => row.observed_on);
  if (days.some((day) => typeof day !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(day) ||
    !Number.isFinite(new Date(day + "T12:00:00Z").getTime()) ||
    new Date(day + "T12:00:00Z").toISOString().slice(0, 10) !== day))
    return data.reference_period;
  const sorted = [...new Set(days as string[])].sort();
  return sorted.length === 1
    ? dateLabel(sorted[0])
    : `${dateLabel(sorted[0])} al ${dateLabel(sorted.at(-1)!)}`;
}
