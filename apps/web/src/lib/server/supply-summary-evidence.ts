/** A source summary must never replace records selected by a price/crop filter. */
export function showsSupplySummaryRecords(filters: URLSearchParams): boolean {
  const viewerControls = new Set(["page", "sheet", "row", "zoom", "locator"]);
  for (const [key, value] of filters) {
    if (value && !viewerControls.has(key)) return false;
  }
  const locator = filters.get("locator");
  return !locator || /^Abastecimiento!row \d+,col \d+; supply-daily-summary-v\d+$/.test(locator);
}
