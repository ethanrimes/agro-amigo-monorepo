/** Resolve a source workbook locator to its in-app sheet and row. */
export function workbookLocation(locator?: string | null): { sheet: string; row: number; column?: number } | null {
  const match = locator?.match(/^([^!]+)!(?:row\s+|[A-Z]+)?(\d+)/i)
    || locator?.match(/^Hoja\s+([^,;]+)[,;]\s*fila\s+(\d+)(?=\s*[,;]|\s*$)/i);
  if (!match) return null;
  const row = Number(match[2]);
  if (!Number.isSafeInteger(row) || row <= 0) return null;
  const numberedColumn = locator?.match(/(?:^|[,;])\s*(?:col(?:umn)?|columna)\s*(\d+)/i);
  const cellColumn = locator?.match(/^[^!]+!([A-Z]+)\d+/i)?.[1].toUpperCase();
  const column = numberedColumn ? Number(numberedColumn[1])
    : cellColumn ? [...cellColumn].reduce((value, letter) => value * 26 + letter.charCodeAt(0) - 64, 0)
    : undefined;
  return column && Number.isSafeInteger(column) && column > 0
    ? { sheet: match[1].trim(), row, column }
    : { sheet: match[1].trim(), row };
}
