import "server-only";
import { database } from "./db";

/** Append-only conflicts, resolutions, and accepted city cohorts advance caches. */
export async function cityPublicationEpoch(): Promise<string> {
  const db = database();
  const base = "SELECT coalesce(max(id),0)::text || ':' || " +
    "(SELECT count(*)::text FROM verified_city_pdf_category_resolution) || ':' || " +
    "(SELECT count(*)::text FROM verified_city_pdf_price_resolution)";
  let rows: { epoch: string }[];
  try {
    ({ rows } = await db.query<{ epoch: string }>(
      base + " || ':' || (SELECT count(*)::text FROM dane_city_cohort_acceptance) AS epoch FROM city_pdf_publication_conflict",
    ));
  } catch (error) {
    // V13 web can precede the private accepted-head schema in staged test deployments.
    if ((error as { code?: string })?.code !== "42P01") throw error;
    ({ rows } = await db.query<{ epoch: string }>(base + " AS epoch FROM city_pdf_publication_conflict"));
  }
  if (!rows[0]) throw new Error("CITY_PUBLICATION_EPOCH_UNAVAILABLE");
  return rows[0].epoch;
}
