/** A retained copy date is distinct from the publisher's observation period. */
export function archiveCopyLabel(retrievedAt?: string): string | null {
  if (!retrievedAt) return null;
  const date = new Date(retrievedAt);
  if (!Number.isFinite(date.getTime())) return null;
  return "Copia archivada el " + date.toLocaleString("es-CO", {
    timeZone: "America/Bogota",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }) + " (Colombia)";
}

/** Distinguish retained versions even when their titles and archive times match. */
export function archiveVersionLabel(id: string, sameTitleIds: string[]): string | null {
  if (sameTitleIds.length < 2) return null;
  let length = Math.min(12, id.length);
  while (length < id.length && sameTitleIds.some((other) => other !== id && other.slice(-length) === id.slice(-length)))
    length = Math.min(length + 4, id.length);
  return `Copia ${id.slice(-length)}`;
}
