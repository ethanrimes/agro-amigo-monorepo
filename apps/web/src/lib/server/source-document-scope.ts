/** Exact reviewed originals outside the app's agricultural subject matter.
 * Retention is independent of visibility: the complete publisher ZIP and its
 * individual original bytes stay archived, including an accidental member.
 */
import registry from "../../../../../shared/source-document-scope.json";

const documents = registry.documents;
if (registry.format !== 1 || documents.length > 100 ||
    new Set(documents.map((document) => document.document_id)).size !== documents.length ||
    documents.some((document) => !/^[a-f0-9]{64}$/.test(document.document_id) ||
      !/^[a-f0-9]{64}$/.test(document.archive_id) ||
      document.scope !== "non-agricultural-administration" ||
      document.media_type !== "application/pdf" || document.publisher !== "DANE" ||
      !Number.isSafeInteger(document.bytes) || document.bytes <= 0 ||
      !/^https:\/\/www\.dane\.gov\.co\/files\/.+[.]zip$/.test(document.source_url) ||
      !document.archive_entry.endsWith(".pdf") ||
      document.native_pages < 1 || document.native_anchors.length < 2)) {
  throw new Error("Invalid reviewed source scope registry");
}

const outsideAgriculture = new Set(documents.map((document) => document.document_id));

/** Call after resolving a document alias; a request cannot choose the scope. */
export function sourceDocumentInApp(documentId: string): boolean {
  return !outsideAgriculture.has(documentId);
}

/** Apply before LIMIT/cursor pagination, preserving every eligible original. */
export const AGRICULTURAL_SOURCE_SCOPE_SQL = documents.length
  ? `d.id NOT IN (${documents.map((document) => `'${document.document_id}'`).join(",")})`
  : "true";
