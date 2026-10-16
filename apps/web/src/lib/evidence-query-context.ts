import { normalizeLabel } from "./label-normalization";
import { unitLabel } from "./market-types";
import { wagePresentationDisplay } from "./wage-basis-display";

type Context = { label: string; value: string };

/** Keep consultation geography visible even when the original has no geography metadata. */
export function evidenceQueryContext(
  metadata: unknown,
  query: URLSearchParams,
  records?: Record<string, unknown>[],
): Context[] {
  const context: Context[] = Array.isArray(metadata)
    ? metadata.filter((item): item is Context => Boolean(item) &&
        typeof item.label === "string" && typeof item.value === "string")
    : [];
  const inherited = [
    ["department", "Departamento de la consulta", /departamento/i],
    ["municipality", "Municipio de la consulta", /municipio/i],
    ["productName", "Producto de la consulta", /producto de la consulta/i],
    ["marketName", "Mercado de la consulta", /mercado de la consulta/i],
    ["providerName", "Proveedor de la consulta", /proveedor de la consulta/i],
    ["stratum", "Estrato de la consulta", /estrato de la consulta/i],
    ["presentation", "Presentación de la consulta", /presentaci[oó]n de la consulta/i],
    ["units", "Unidades de la consulta", /unidades de la consulta/i],
    ["currency", "Moneda de la consulta", /moneda de la consulta/i],
  ] as const;
  for (const [key, label, existing] of inherited) {
    const value = query.get(key)?.trim();
    // Numeric administrative IDs use the server's verified place labels.
    const numericPlace = (key === "department" || key === "municipality") && /^\d/.test(value || "");
    if (value && !numericPlace && !context.some((item) => existing.test(item.label)))
      context.push({ label, value: value.slice(0, 220) });
  }
  const day = query.get("month")?.trim();
  const time = day ? Date.parse(`${day}T12:00:00Z`) : NaN;
  if (day && /^\d{4}-\d{2}-\d{2}$/.test(day) &&
      Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === day) {
    const monthlySupply = day.endsWith("-01") && records?.some((record) =>
      record.period_start === day && typeof record.food_name === "string" &&
      typeof record.quantity_kg === "number" && Number.isFinite(record.quantity_kg) &&
      typeof record.reporting_days === "number" && Number.isFinite(record.reporting_days),
    );
    if (monthlySupply) {
      if (!context.some((item) => /mes del abastecimiento consultado/i.test(item.label)))
        context.push({ label: "Mes del abastecimiento consultado", value: new Intl.DateTimeFormat(
          "es-CO", { month: "long", year: "numeric", timeZone: "UTC" },
        ).format(new Date(time)) });
    } else if (!context.some((item) => /fecha del dato consultado/i.test(item.label))) {
      context.push({ label: "Fecha del dato consultado", value: day });
    }
  }
  const consultedName = context.find((item) =>
    /^Producto de la consulta$/i.test(item.label))?.value || "";
  return context.map((item) => {
    if (/^Unidades de la consulta$/i.test(item.label) &&
        ["kg", "unit", "litre", "125kg"].includes(item.value))
      return { ...item, value: unitLabel(item.value) };
    if (/^Municipio de la consulta$/i.test(item.label))
      return { ...item, value: normalizeLabel(item.value, "place") };
    return /^Presentaci[oó]n de la consulta$/i.test(item.label)
      ? { ...item, value: wagePresentationDisplay(
          consultedName, normalizeLabel(item.value, "presentation"),
        ) }
      : item;
  });
}
