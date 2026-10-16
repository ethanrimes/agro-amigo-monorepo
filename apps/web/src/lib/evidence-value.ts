import { number } from "./market-types";

/** Years and physical row identifiers are labels, rather than measured amounts. */
export function evidenceValue(key: string, value: unknown): string {
  if (value === null) return "Sin dato";
  if (Array.isArray(value)) return value.join(" · ");
  if (typeof value === "number") {
    if (
      Number.isInteger(value) &&
      (key === "reference_year" || key === "source_row")
    ) {
      return String(value);
    }
    return number(value);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Bind the unit explanation to normalized, persisted quote records rather
 * than to an unverified locator supplied in a browser query. */
export function evidenceUnitNote(records: Record<string, unknown>[] = []): string | null {
  return records.some(row => row.unit === "kg" && typeof row.price === "number"
    && typeof row.source_locator === "string"
    && row.source_locator.endsWith("; COP/tonelada dividido entre 1000 = COP/kg"))
    ? "El archivo original muestra precios por tonelada. En la app se muestran por kilogramo: el precio original se divide entre 1.000."
    : null;
}
