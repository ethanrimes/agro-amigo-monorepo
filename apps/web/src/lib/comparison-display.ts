import type { ComparisonData, ComparisonKind, ComparisonQuote } from "./comparison-types";
import { summarizeComparisons } from "./comparison-math";
import { normalizeLabel } from "./label-normalization";
import { inputLocationDisplayLabel } from "./input-locations";

function place(kind: ComparisonKind, scope: string, id: string, name: string): string {
  if (kind === "inputs" && scope === "municipality") {
    // The ID remains the exact selector; only its displayed place spelling is normalized.
    try {
      const parts: unknown = JSON.parse(id);
      if (Array.isArray(parts) && parts.length === 2 &&
          typeof parts[0] === "string" && typeof parts[1] === "string")
        return inputLocationDisplayLabel(parts[0], parts[1]);
    } catch { /* Preserve an unknown exact selector's display name. */ }
  }
  return normalizeLabel(name, "place");
}

function quote(quoted: ComparisonQuote, kind: ComparisonKind, scope: string): ComparisonQuote {
  return {
    ...quoted,
    name: normalizeLabel(quoted.name, kind === "inputs" ? "input" : "product"),
    category: normalizeLabel(quoted.category, "category"),
    category_path: quoted.category_path.map((part) => normalizeLabel(part, "category")),
    location_name: place(kind, scope, quoted.location_id, quoted.location_name),
    ...(quoted.department ? { department: normalizeLabel(quoted.department, "place") } : {}),
  };
}

/** Map presentation fields only, after quote selection and comparison arithmetic. */
export function comparisonDisplay(data: ComparisonData): ComparisonData {
  const { kind } = data;
  const scope = data.filters.scope;
  const locationName = (id: string, fallback: string) =>
    data.locations.find((location) => location.id === id)?.name || fallback;
  const rows = data.rows.map((row) => ({ ...row,
    a: quote(row.a, kind, scope),
    b: row.b && { ...row.b,
      ...(row.b.sources ? { sources: row.b.sources.map((source) => quote(source, kind, scope)) } : {}),
    },
  }));
  return {
    ...data,
    locations: data.locations.map((location) => ({ ...location,
      name: place(kind, scope, location.id, location.name),
    })),
    a_name: place(kind, scope, data.filters.a, locationName(data.filters.a, data.a_name)),
    b_name: data.filters.b === "__national__" ? data.b_name
      : place(kind, scope, data.filters.b, locationName(data.filters.b, data.b_name)),
    rows,
    // Category spellings can converge; grouping the normalized rows retains
    // the actual count-weighted mean instead of duplicating display groups.
    summaries: summarizeComparisons(rows).summaries,
  };
}
