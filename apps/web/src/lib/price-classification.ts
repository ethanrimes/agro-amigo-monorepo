/** The hero describes the same current filtered quotes as its price. Historical
 * paths remain in retained records and cannot override a newer scoped quote. */
export function currentClassifications(
  quotes: { category_path?: string[] | null; category?: string | null; date?: string }[],
  fallbackCategory: string,
  currentDate?: string,
): string[][] {
  const paths = quotes.filter((quote) => !currentDate || quote.date === currentDate).map((quote) => quote.category_path?.filter(Boolean) || (quote.category ? quote.category.split(' > ') : [])).filter((path) => path.length);
  const distinct = [...new Map(paths.map((path) => [JSON.stringify(path), path])).values()];
  return distinct.length ? distinct : fallbackCategory ? [[fallbackCategory]] : [];
}
