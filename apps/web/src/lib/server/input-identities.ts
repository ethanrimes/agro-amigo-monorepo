import "server-only";
import { database } from "./db";
import { currentInputIdentities, type InputRevision, type InputDocumentRevision } from "../input-revisions";

/** A bounded metadata read; source bytes and retained observations are untouched. */
export async function reconcileInputCatalog<T extends InputRevision>(rows: T[]): Promise<T[]> {
  if (rows.length < 2) return rows;
  const documentIds = [...new Set(rows.map((row) => row.document_id))];
  const documents = await database().query<InputDocumentRevision>(
    "SELECT id,source_url,retrieved_at FROM source_document WHERE id=ANY($1::text[])", [documentIds],
  );
  return currentInputIdentities(rows, documents.rows);
}
