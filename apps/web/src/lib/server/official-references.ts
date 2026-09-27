import "server-only";
import type { OfficialPrice } from "../official-types";
import { database } from "./db";
import { summaryReference } from "./summary-references";
import { snapshotCache } from "./snapshot-cache";

type LatestOfficialPrice = OfficialPrice & { previous_price: number | null };
const latestSnapshot = snapshotCache<LatestOfficialPrice[]>();
const historySnapshot = snapshotCache<{ reference: OfficialPrice; history: OfficialPrice[] } | null>();

/** Match published_official_price eligibility and revision order. First seek
 * the newest eligible date through official_quote_identity, then compare only
 * revisions on that date. Indexed review lookups avoid rescanning a materialized
 * review list for every historical quote. Previous price uses a distinct date.
 */
export const LATEST_OFFICIAL_REFERENCES_SQL = `
  WITH RECURSIVE identities(quote_key) AS (
    (SELECT quote_key FROM official_price_quote ORDER BY quote_key LIMIT 1)
    UNION ALL
    SELECT n.quote_key FROM identities i CROSS JOIN LATERAL (
      SELECT quote_key FROM official_price_quote WHERE quote_key>i.quote_key
      ORDER BY quote_key LIMIT 1
    ) n
  )
  SELECT p.*,previous.price AS previous_price FROM identities i CROSS JOIN LATERAL (
    SELECT q.observed_on FROM official_price_quote q
    WHERE q.quote_key=i.quote_key
      AND q.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
    ORDER BY q.observed_on DESC LIMIT 1
  ) latest_day CROSS JOIN LATERAL (
    SELECT q.*,d.source_url FROM official_price_quote q
    JOIN source_document d ON d.id=q.document_id
    WHERE q.quote_key=i.quote_key AND q.observed_on=latest_day.observed_on
      AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
        AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
      AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
        AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
    ORDER BY d.retrieved_at DESC,q.parsed_at DESC,q.source_locator LIMIT 1
  ) p LEFT JOIN LATERAL (
    SELECT prior.price FROM (
      SELECT q.observed_on FROM official_price_quote q
      WHERE q.quote_key=p.quote_key AND q.observed_on<p.observed_on
        AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
          AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
        AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
          AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      ORDER BY q.observed_on DESC LIMIT 1
    ) previous_day CROSS JOIN LATERAL (
      SELECT q.price FROM official_price_quote q JOIN source_document d ON d.id=q.document_id
      WHERE q.quote_key=p.quote_key AND q.observed_on=previous_day.observed_on
        AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=q.document_id
          AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=q.observed_on))
        AND NOT EXISTS(SELECT 1 FROM official_source_review r WHERE r.document_id=q.document_id
          AND r.source_locator=q.source_locator AND r.created_at>=q.parsed_at)
      ORDER BY d.retrieved_at DESC,q.parsed_at DESC,q.source_locator LIMIT 1
    ) prior
  ) previous ON true`;

export function latestOfficialReferences(): Promise<LatestOfficialPrice[]> {
  return latestSnapshot("all", async () => (await database().query<LatestOfficialPrice>(LATEST_OFFICIAL_REFERENCES_SQL)).rows);
}

export async function officialReferences(q: URLSearchParams) {
  const id = q.get("id") || "";
  if (id) {
    if (id.startsWith("summary-")) return summaryReference(id);
    if (!/^[a-f0-9]{64}$/.test(id)) return null;
    return historySnapshot(id, async () => {
      const rows = (await database().query<OfficialPrice>(
        `SELECT q.*,d.source_url FROM published_official_price q JOIN source_document d ON d.id=q.document_id WHERE quote_key=$1 AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY observed_on`,
        [id],
      )).rows;
      return rows.length ? { reference: rows.at(-1)!, history: rows } : null;
    });
  }
  const query = (q.get("q") || "").slice(0, 150),
    category = (q.get("category") || "").slice(0, 150),
    publisher = (q.get("publisher") || "").slice(0, 150),
    currency = (q.get("currency") || "").slice(0, 3),
    page = Math.floor(Math.max(0, Math.min(500, Number(q.get("page")) || 0)));
  const fold = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const search = fold(query), snapshot = await latestOfficialReferences();
  const filtered = snapshot.filter((row) =>
    (!search || fold(`${row.product_name} ${row.market} ${row.basis}`).includes(search)) &&
    (!category || row.category === category) && (!publisher || row.publisher === publisher) &&
    (!currency || row.currency === currency),
  ).sort((a, b) => b.observed_on.localeCompare(a.observed_on) ||
    a.product_name.localeCompare(b.product_name) || a.market.localeCompare(b.market) || a.quote_key.localeCompare(b.quote_key));
  const options = (field: "category" | "publisher" | "currency") => [...new Set(snapshot.map((row) => row[field]))].sort();
  return {
    rows: filtered.slice(page * 48, (page + 1) * 48), total: filtered.length, page,
    filters: { query, category, publisher, currency },
    options: { categories: options("category"), publishers: options("publisher"), currencies: options("currency") },
  };
}
