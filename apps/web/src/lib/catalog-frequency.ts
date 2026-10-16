import type { Product } from "./market-types";

const frequencies: Record<string, string> = {
  daily: "Diario", diario: "Diario", diaria: "Diario",
  weekly: "Semanal", semanal: "Semanal", "semana de referencia": "Semanal",
  monthly: "Mensual", mensual: "Mensual",
  fortnightly: "Quincenal", quincenal: "Quincenal",
  quarterly: "Trimestral", trimestral: "Trimestral",
  semiannual: "Semestral", semestral: "Semestral", semestre: "Semestral",
  annual: "Anual", annually: "Anual", anual: "Anual",
};

/** Describe the source's stated period; absent metadata is not a daily report. */
export function officialFrequency(periodType: unknown, series: string): string | null {
  if (typeof periodType === "string" && periodType.trim()) {
    const key = periodType.normalize("NFKD").replace(/\p{M}/gu, "")
      .toLocaleLowerCase("es-CO").trim().replace(/\s+/g, " ");
    return frequencies[key] || null;
  }
  const declared = series.toLowerCase().split(/[^a-z]+/)
    .map((word) => frequencies[word]).filter(Boolean);
  return new Set(declared).size === 1 ? declared[0] : null;
}

/** Compatibility field; only the explicit label is a frequency guarantee. */
export function legacyReferencePeriod(frequency: string | null): Product["period"] {
  return frequency === "Mensual" ? "monthly" : frequency === "Semanal" ? "weekly" : "daily";
}
