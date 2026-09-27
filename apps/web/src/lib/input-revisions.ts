export type InputRevision = {
  id: string; name: string; presentation: string; observed_on: string;
  department: string; municipality?: string; document_id: string; source_locator: string;
  brand?: string | null; registration?: string | null;
};
export type InputDocumentRevision = { id: string; source_url: string; retrieved_at: string | Date };

/** Only reconcile known old/native locator spellings for the very same original
 * worksheet row. Similar product names or adjacent row positions are not proof. */
export function inputSourceCell(locator: string | null | undefined): string | null {
  if (typeof locator !== "string") return null;
  const modern = locator.match(/^(.+?)!row\s+(\d+)(?:;.*)?$/i);
  const legacy = locator.match(/^Hoja\s+(.+?),\s*fila\s+(\d+)(?:;.*)?$/i);
  const match = modern || legacy;
  return match ? JSON.stringify([match[1].trim(), Number(match[2])]) : null;
}

/** Older nameless commercial identities stay readable by ID. Only catalog
 * aliases proven superseded by a newer revision of the same source cell hide. */
export function currentInputIdentities<T extends InputRevision>(rows: T[], documents: InputDocumentRevision[]): T[] {
  const docs = new Map(documents.map(d => [d.id, d]));
  const groups = new Map<string, T[]>();
  const keyFor = (row: T) => {
    const doc = docs.get(row.document_id), cell = inputSourceCell(row.source_locator);
    if (!doc || !cell) return null;
    return JSON.stringify([doc.source_url, cell, row.observed_on, row.department, row.municipality || '', row.name.trim().toLocaleLowerCase(), row.presentation.trim().toLocaleLowerCase()]);
  };
  for (const row of rows) {
    const key = keyFor(row);
    if (key) groups.set(key, [...(groups.get(key) || []), row]);
  }
  return rows.filter(row => {
    if (row.brand?.trim() || row.registration?.trim()) return true;
    const key = keyFor(row);
    if (!key) return true;
    const oldDate = new Date(docs.get(row.document_id)!.retrieved_at).getTime();
    const replacements = (groups.get(key) || []).filter(candidate => candidate.id !== row.id &&
      Boolean(candidate.brand?.trim() || candidate.registration?.trim()) &&
      new Date(docs.get(candidate.document_id)!.retrieved_at).getTime() > oldDate);
    // Conflicting new commercial identities require review, not an arbitrary pick.
    return new Set(replacements.map(candidate => candidate.id)).size !== 1;
  });
}
