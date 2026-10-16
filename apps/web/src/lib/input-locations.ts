import { departmentKey, departmentLabel } from "./filter-labels";
import { normalizeLabel } from "./label-normalization";

type InputLocationRow = {
  id?: string;
  department?: string;
  municipality?: string;
  observed_on?: string;
  price?: number;
  document_id?: string;
  source_locator?: string;
};

/** NFC and letter case are the only municipal equivalences. Accents remain distinct. */
export function municipalityKey(value: string): string {
  return value.normalize("NFC").toLocaleLowerCase("es");
}

export function municipalityLabel(value: string): string {
  return value.normalize("NFC").split(" ").map((word, index) => {
    const lower = word.toLocaleLowerCase("es");
    if (/^[a-z](?:\.[a-z])+\.?$/i.test(word)) return word.toLocaleUpperCase("es");
    return index && ["de", "del", "la", "las", "los", "y"].includes(lower)
      ? lower : lower.slice(0, 1).toLocaleUpperCase("es") + lower.slice(1);
  }).join(" ");
}

/** One current quote per exact product, approved department alias and case-only municipality. */
export function latestInputLocations<T extends InputLocationRow>(rows: T[]): T[] {
  const current = new Map<string, T>();
  for (const row of rows) {
    const key = JSON.stringify([row.id, departmentKey(row.department || ""), municipalityKey(row.municipality || "")]);
    const previous = current.get(key);
    const date = row.observed_on || "";
    const previousDate = previous?.observed_on || "";
    const tie = (value: T) => JSON.stringify([value.document_id || "", value.source_locator || ""]);
    if (!previous || date > previousDate || (date === previousDate &&
      ((row.price || 0) < (previous.price || 0) ||
        (row.price === previous.price && tie(row) < tie(previous))))) current.set(key, row);
  }
  // Return the literal winning source row; historical rows are never modified.
  return [...current.values()];
}

/** Display a municipality with reviewed spelling while preserving raw selector values. */
export function inputMunicipalityDisplayLabel(municipality = ""): string {
  return municipality ? normalizeLabel(municipality, "place") : "";
}

/** Full location names are for display only; selector construction stays below and literal. */
export function inputLocationDisplayLabel(department: string, municipality = ""): string {
  const shownDepartment = normalizeLabel(department, "place");
  const shownMunicipality = inputMunicipalityDisplayLabel(municipality);
  return shownMunicipality ? `${shownMunicipality}, ${shownDepartment}` : shownDepartment;
}

/** Keep the existing non-input map name path; format only named input municipalities. */
export function mapPointDisplayName(
  kind: string, name: string, region = "", municipality = "",
): string {
  return kind === "input" && municipality
    ? inputLocationDisplayLabel(region, municipality)
    : normalizeLabel(name, "place");
}

export function inputLocationId(department: string, municipality = "", municipal = false): string {
  const label = departmentLabel(department);
  return municipal ? JSON.stringify([label, municipalityLabel(municipality)]) : label;
}

export function canonicalInputLocation(location: string, municipal: boolean): string {
  if (!location || location === "__national__") return location;
  if (!municipal) return inputLocationId(location);
  try {
    const values = JSON.parse(location);
    return Array.isArray(values) && values.length === 2 && values.every((value) => typeof value === "string")
      ? inputLocationId(values[0], values[1], true) : location;
  } catch { return location; }
}
