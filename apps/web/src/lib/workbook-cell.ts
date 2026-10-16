export type WorkbookCell = {
  value: string | number | boolean | null;
  type: string;
  number_format?: string;
};

// Both browser and server caches must change when preview semantics change.
export const WORKBOOK_PREVIEW_VERSION = "native-formats-v3";

// Allow the server's bounded 45-second original-preview request to finish,
// including the source authorization query and response transfer.
export const WORKBOOK_REQUEST_TIMEOUT_MS = 60_000;

/** Hide binary-formula tails only when a shorter decimal is within float noise. */
function sourceDecimal(value: number): number {
  if (!/\.\d*(?:0{5,}|9{5,})\d*$/.test(String(value))) return value;
  const tolerance = Number.EPSILON * Math.abs(value) * 4;
  for (let places = 0; places <= 12; places++) {
    const rounded = Number(value.toFixed(places));
    if (Math.abs(value - rounded) <= tolerance) return rounded;
  }
  return value;
}

/** Preserve raw source values; Excel's percent format changes only their display. */
export function workbookCellText(cell: WorkbookCell): string {
  if (cell.value === null) return "";
  if (typeof cell.value !== "number") return String(cell.value);
  const value = sourceDecimal(cell.value);
  // Semicolons inside literals are not section boundaries. Negative and zero
  // sections can have different precision from positive cells.
  const sections = (cell.number_format || "General").match(/(?:"[^"]*"|\\.|[^;])+/g) || [];
  const section = sections[value < 0 && sections.length > 1 ? 1 : value === 0 && sections.length > 2 ? 2 : 0] || "General";
  const tokens = section.replace(/"[^"]*"|\\.|\[[^\]]*\]|_.|\*./g, "");
  const percentCount = (tokens.match(/%/g) || []).length;
  const literalPercent = /"[^"]*%[^"]*"|\\%/.test(section);
  if (!percentCount && !literalPercent)
    return value.toLocaleString("es-CO", {
      maximumFractionDigits: 12,
      // Group only when the source format requests grouping. General cells
      // include years and identifiers; 2021 must not become 2.021.
      // Explicit price formats still group without rounding the raw decimals.
      useGrouping: tokens.includes(","),
    });
  const decimals = tokens.match(/[0#?]+\.([0#?]+)/)?.[1] || "";
  const places = Math.min(decimals.length, 12);
  const parentheses = value < 0 && tokens.includes("(") && tokens.includes(")");
  const scaled = value * 100 ** percentCount;
  const text = (parentheses ? Math.abs(scaled) : scaled).toLocaleString("es-CO", {
    minimumFractionDigits: Math.min((decimals.match(/0/g) || []).length, places),
    maximumFractionDigits: places,
    useGrouping: tokens.includes(","),
  });
  const rendered = `${text}${"%".repeat(percentCount || 1)}`;
  return parentheses ? `(${rendered})` : rendered;
}
