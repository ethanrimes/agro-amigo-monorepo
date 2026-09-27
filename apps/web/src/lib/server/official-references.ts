import "server-only";
import type { OfficialPrice } from "../official-types";
import { database } from "./db";
import { summaryReference } from "./summary-references";
import { snapshotCache } from "./snapshot-cache";

type LatestOfficialPrice = OfficialPrice & { previous_price: number | null };
const latestSnapshot = snapshotCache<LatestOfficialPrice[]>();
const historySnapshot = snapshotCache<{ reference: OfficialPrice; history: OfficialPrice[] } | null>();

/** Ingestion owns revision selection; request reads stay proportional to catalog size. */
export const LATEST_OFFICIAL_REFERENCES_SQL = `
  SELECT payload FROM official_catalog_current
  WHERE payload IS NOT NULL AND NOT dirty AND version='official-catalog-v1'
    AND (payload->>'observed_on')::date <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date`;

export function latestOfficialReferences(): Promise<LatestOfficialPrice[]> {
  return latestSnapshot("all", async () => (await database().query<{ payload: LatestOfficialPrice }>(LATEST_OFFICIAL_REFERENCES_SQL)).rows.map((row) => row.payload));
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
