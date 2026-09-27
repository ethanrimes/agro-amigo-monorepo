export type WorkbookCell = {
  value: string | number | boolean | null;
  type: string;
  number_format?: string;
};

// Both browser and server caches must change when preview semantics change.
export const WORKBOOK_PREVIEW_VERSION = "native-formats-v2";

/** Preserve raw source values; Excel's percent format changes only their display. */
export function workbookCellText(cell: WorkbookCell): string {
  if (cell.value === null) return "";
  if (typeof cell.value !== "number") return String(cell.value);
  const value = cell.value;
  // Semicolons inside literals are not section boundaries. Negative and zero
  // sections can have different precision from positive cells.
  const sections = (cell.number_format || "General").match(/(?:"[^"]*"|\\.|[^;])+/g) || [];
  const section = sections[value < 0 && sections.length > 1 ? 1 : value === 0 && sections.length > 2 ? 2 : 0] || "General";
  const tokens = section.replace(/"[^"]*"|\\.|\[[^\]]*\]|_.|\*./g, "");
  const percentCount = (tokens.match(/%/g) || []).length;
  const literalPercent = /"[^"]*%[^"]*"|\\%/.test(section);
  if (!percentCount && !literalPercent)
    return value.toLocaleString("es-CO", { maximumFractionDigits: 12 });
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
