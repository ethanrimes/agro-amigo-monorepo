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
