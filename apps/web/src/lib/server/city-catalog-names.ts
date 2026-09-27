import "server-only";
import { database } from "./db";
import { CITY_CATALOG_NAMES_SQL } from "./catalog-sql";

export type CityCatalogName = { product_id: string; product_name: string; latest_date: string | null };
let snapshot: { expires: number; rows: CityCatalogName[] } | undefined;
let pending: Promise<CityCatalogName[]> | undefined;

/** Shared by canonical card selection and the unified catalog search aliases. */
export async function cityCatalogNames(): Promise<CityCatalogName[]> {
  if (snapshot && snapshot.expires > Date.now()) return snapshot.rows;
  if (pending) return pending;
  pending = database().query<CityCatalogName>(CITY_CATALOG_NAMES_SQL).then(({ rows }) => {
    snapshot = { rows, expires: Date.now() + 300_000 };
    return rows;
  }).finally(() => { pending = undefined; });
  return pending;
}
