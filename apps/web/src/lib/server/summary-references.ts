import "server-only";
import { createHash } from "node:crypto";
import type { OfficialPrice } from "../official-types";
import { database } from "./db";

type SummaryRow = {
  product_name: string;
  market_name: string;
  unit: string;
  observed_on: string;
  price: number;
  change_percent: number | null;
  document_id: string;
  source_locator: string;
  source_url: string;
  details: Record<string, unknown>;
};
export type SummaryReference = OfficialPrice & { canonical_product_id: string | null };
const validSource = `h.series='dane-monthly-summary'
  AND h.observed_on <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=h.document_id
    AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=h.observed_on))`;
const canonicalName = (name: string) => name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
const keyFor = (row: Pick<SummaryRow, "product_name" | "market_name" | "unit">) =>
  "summary-" + createHash("sha256").update(JSON.stringify([
    "dane-monthly-summary", row.product_name, row.market_name, row.unit,
  ])).digest("hex");

function observation(row: SummaryRow, productId: string | null): SummaryReference {
  return {
    quote_key: keyFor(row),
    product_id: productId || "summary-product:" + createHash("sha256").update(row.product_name).digest("hex"),
    canonical_product_id: productId,
    product_name: row.product_name,
    category: "Productos mayoristas",
    publisher: "DANE · SIPSA",
    series: "dane-monthly-summary",
    basis: "Promedio mensual publicado por ciudad",
    currency: "COP",
    unit: row.unit,
    market: row.market_name,
    observed_on: row.observed_on,
    period_start: row.observed_on.slice(0, 8) + "01",
    price: row.price,
    min_price: null,
    max_price: null,
    document_id: row.document_id,
    source_locator: row.source_locator,
    source_url: row.source_url,
    details: {
      ...row.details,
      source_product: row.product_name,
      original_price: row.price,
      published_unit: row.unit,
      change_percent: row.change_percent,
      source_note: "Nombre y ciudad literales del anexo. Los asteriscos de la fuente se conservan; no se asigna una variedad ni un mercado individual por inferencia.",
    },
  };
}

let snapshot: { expires: number; rows: SummaryReference[] } | undefined;
let pending: Promise<SummaryReference[]> | undefined;
/** Latest identities only are cached; an individual history is queried on demand. */
export async function latestSummaryReferences(): Promise<SummaryReference[]> {
  if (snapshot && snapshot.expires > Date.now()) return snapshot.rows;
  if (pending) return pending;
  pending = (async () => {
    const [data, products] = await Promise.all([
      database().query<SummaryRow>(`
        SELECT DISTINCT ON(h.product_name,h.market_name,h.unit) h.*,d.source_url
        FROM historical_price h JOIN source_document d ON d.id=h.document_id
        WHERE ${validSource}
        ORDER BY h.product_name,h.market_name,h.unit,h.observed_on DESC,d.retrieved_at DESC,h.document_id,h.source_locator
      `),
      database().query<{ id: string; name: string }>("SELECT id,name FROM product"),
    ]);
    const names = new Map<string, string[]>();
    for (const product of products.rows) {
      const key = canonicalName(product.name);
      names.set(key, [...(names.get(key) || []), product.id]);
    }
    const rows = data.rows.map((row) => {
      const matches = names.get(canonicalName(row.product_name)) || [];
      return observation(row, matches.length === 1 ? matches[0] : null);
    });
    snapshot = { rows, expires: Date.now() + 300_000 };
    return rows;
  })().finally(() => { pending = undefined; });
  return pending;
}

export async function summaryReference(id: string) {
  if (!/^summary-[a-f0-9]{64}$/.test(id)) return null;
  const latest = (await latestSummaryReferences()).find((row) => row.quote_key === id);
  if (!latest) return null;
  const { rows } = await database().query<SummaryRow>(`
    SELECT DISTINCT ON(h.observed_on) h.*,d.source_url
    FROM historical_price h JOIN source_document d ON d.id=h.document_id
    WHERE ${validSource} AND h.product_name=$1 AND h.market_name=$2 AND h.unit=$3
    ORDER BY h.observed_on,d.retrieved_at DESC,h.document_id,h.source_locator
  `, [latest.product_name, latest.market, latest.unit]);
  const history = rows.map((row) => observation(row, latest.canonical_product_id));
  return history.length ? { reference: history.at(-1)!, history } : null;
}

export async function summaryReferencesForProduct(exactCanonicalName: string): Promise<OfficialPrice[]> {
  const name = canonicalName(exactCanonicalName);
  return (await latestSummaryReferences()).filter((row) =>
    row.canonical_product_id !== null && canonicalName(row.product_name) === name,
  );
}
