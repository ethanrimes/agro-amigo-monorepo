import { normalizeLabel } from "./label-normalization";
import { categoryMatches } from "./category-hierarchy";

/** Group only reviewed display spellings; keep the literal categories for SQL. */
export function categoryOptions(raw: string[]): string[] {
  return [...new Set(raw.map((value) => normalizeLabel(value, "category")))];
}

export function categoryVariants(raw: string[], selected: string): string[] {
  if (!selected) return [];
  return [...new Set(raw.filter((value) => categoryMatches(value, selected)))];
}

/** The stored JSON and original document remain literal; only named UI fields change. */
export function displayDetails(details: Record<string, unknown>, kind: string): Record<string, unknown> {
  const shown = { ...details };
  for (const [key, domain] of Object.entries({
    Ciudad: "place", Departamento: "place", Grupo: "category",
    ...(kind === "wholesale" ? { Producto: "product" } : {}),
  }) as [string, "place" | "category" | "product"][]) {
    if (typeof shown[key] === "string") shown[key] = normalizeLabel(shown[key], domain);
  }
  return shown;
}
