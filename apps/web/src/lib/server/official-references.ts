import "server-only";
import { database } from "./db";
import { summaryReference } from "./summary-references";
export async function officialReferences(q: URLSearchParams) {
  const db = database(),
    id = q.get("id") || "";
  if (id) {
    if (id.startsWith("summary-")) return summaryReference(id);
    if (!/^[a-f0-9]{64}$/.test(id)) return null;
    const rows = (
      await db.query(
        `SELECT q.*,d.source_url FROM published_official_price q JOIN source_document d ON d.id=q.document_id WHERE quote_key=$1 AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY observed_on`,
        [id],
      )
    ).rows;
    return rows.length ? { reference: rows.at(-1), history: rows } : null;
  }
  const query = (q.get("q") || "").slice(0, 150),
    category = (q.get("category") || "").slice(0, 150),
    publisher = (q.get("publisher") || "").slice(0, 150),
    currency = (q.get("currency") || "").slice(0, 3),
    page = Math.max(0, Math.min(500, Number(q.get("page")) || 0));
  const search = query
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const latest = `SELECT DISTINCT ON(quote_key) q.* FROM published_official_price q WHERE observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY quote_key,observed_on DESC`;
  const filter = `($1='' OR translate(lower(product_name || ' ' || market || ' ' || basis),'áéíóúüñ','aeiouun') LIKE '%' || $1 || '%') AND ($2='' OR category=$2) AND ($3='' OR publisher=$3) AND ($4='' OR currency=$4)`;
  // Materialize the published snapshot once. Counts, pickers and pagination
  // share that snapshot; only the displayed rows need source-document joins.
  // The previous three parallel scans competed for the small demo DB pool.
  const result = (await db.query(
    `WITH latest AS MATERIALIZED (${latest}),
      filtered AS MATERIALIZED (SELECT * FROM latest WHERE ${filter}),
      paged AS (SELECT * FROM filtered ORDER BY observed_on DESC,product_name,market,quote_key LIMIT 48 OFFSET $5)
     SELECT
       COALESCE((SELECT json_agg(r ORDER BY r.observed_on DESC,r.product_name,r.market,r.quote_key)
         FROM (SELECT p.*,d.source_url FROM paged p JOIN source_document d ON d.id=p.document_id) r),'[]'::json) AS rows,
       (SELECT count(*) FROM filtered) AS total,
       COALESCE((SELECT json_agg(o) FROM (SELECT DISTINCT category,publisher,currency FROM latest
         ORDER BY category,publisher,currency) o),'[]'::json) AS options`,
    [search, category, publisher, currency, page * 48],
  )).rows[0];
  const options = result.options as { category: string; publisher: string; currency: string }[];
  return {
    rows: result.rows,
    total: Number(result.total),
    page,
    filters: { query, category, publisher, currency },
    options: {
      categories: [...new Set(options.map((x) => x.category))],
      publishers: [...new Set(options.map((x) => x.publisher))],
      currencies: [...new Set(options.map((x) => x.currency))],
    },
  };
}
