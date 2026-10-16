/** Native PDF locators use one-based pages; workbook rows are not PDF pages. */
export function pdfLocationPage(locator?: string | null): number | undefined {
  const match = locator?.match(/^PDF page ([1-9][0-9]{0,4})(?:[\s,;]|$)/);
  return match ? Number(match[1]) : undefined;
}

export function evidencePage(page: string | number | null | undefined, locator?: string | null): number {
  const explicit = Number(page);
  return Number.isSafeInteger(explicit) && explicit > 0 && explicit <= 99999
    ? explicit : pdfLocationPage(locator) || 1;
}
