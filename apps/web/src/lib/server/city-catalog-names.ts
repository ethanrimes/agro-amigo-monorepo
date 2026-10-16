import "server-only";
import { database } from "./db";
import { CITY_CATALOG_NAMES_SQL } from "./catalog-sql";
import { cityPublicationEpoch } from "./city-publication-epoch";

export type CityCatalogName = { product_id: string; product_name: string; latest_date: string | null };
let snapshot: { epoch: string; expires: number; rows: CityCatalogName[] } | undefined;
let pending: { epoch: string; work: Promise<CityCatalogName[]> } | undefined;

/** Shared by canonical card selection and the unified catalog search aliases. */
export async function cityCatalogNames(): Promise<CityCatalogName[]> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const epoch = await cityPublicationEpoch();
    let rows: CityCatalogName[];
    if (snapshot?.epoch === epoch && snapshot.expires > Date.now()) rows = snapshot.rows;
    else {
      if (pending?.epoch !== epoch) {
        const work = database().query<CityCatalogName>(CITY_CATALOG_NAMES_SQL).then(({ rows }) => {
          snapshot = { epoch, rows, expires: Date.now() + 300_000 };
          return rows;
        }).finally(() => { if (pending?.work === work) pending = undefined; });
        pending = { epoch, work };
      }
      rows = await pending.work;
    }
    if (epoch === await cityPublicationEpoch()) return rows;
  }
  throw new Error("CITY_PUBLICATION_CHANGED_DURING_READ");
}
