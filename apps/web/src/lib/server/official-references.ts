import "server-only";
import type { OfficialPrice } from "../official-types";
import { database } from "./db";
import { summaryReference } from "./summary-references";
import { snapshotCache } from "./snapshot-cache";
import { officialMarketRegions } from "./official-market-regions";
import { normalizeLabel, normalizeOfficialLabels, officialProductSearchNames } from "../label-normalization";
import { categoryMatches } from "../category-hierarchy";
import {
  ACELGA_WEEKLY_CANONICAL_KEY, ACELGA_WEEKLY_KEYS,
  collapseAcelgaWeeklyCatalog, isAcelgaWeeklyConflict, isAcelgaWeeklyKey,
  mergeAcelgaWeeklyHistory,
} from "./acelga-weekly-continuity";
import {
  collapseWeeklyCorabastosCatalog, isWeeklyCorabastosConflict,
  mergeWeeklyCorabastosHistory, weeklyCorabastosGroups,
  expectedWeeklyCorabastosKey, WEEKLY_CORABASTOS_MARKETS,
  type WeeklyCorabastosGroup,
} from "./weekly-corabastos-continuity";
import {
  MINORISTA_WEEKLY_CANONICAL_KEY, MINORISTA_WEEKLY_KEYS,
  collapseMinoristaWeeklyCatalog, isMinoristaWeeklyConflict, isMinoristaWeeklyKey,
  mergeMinoristaWeeklyHistory, standaloneMinoristaWeeklyHistory,
} from "./minorista-weekly-continuity";
import {
  AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY, AGUACATE_BUCARAMANGA_WEEKLY_KEYS,
  collapseAguacateBucaramangaWeeklyCatalog, isAguacateBucaramangaWeeklyConflict,
  isAguacateBucaramangaWeeklyKey, mergeAguacateBucaramangaWeeklyHistory,
  standaloneAguacateBucaramangaWeeklyHistory,
} from "./aguacate-bucaramanga-weekly-continuity";
import {
  capitalizationWeeklyGroups, collapseCapitalizationWeeklyCatalog,
  isWeeklyCapitalizationConflict, mergeCapitalizationWeeklyHistory,
  MAX_WEEKLY_CAPITALIZATION_KEYS,
  type CapitalizationGroup,
} from "./weekly-capitalization-continuity";

function sourceTerms(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(sourceTerms);
  if (value && typeof value === "object") return Object.values(value).flatMap(sourceTerms);
  return [];
}

type LatestOfficialPrice = OfficialPrice & { previous_price: number | null };
const latestSnapshot = snapshotCache<LatestOfficialPrice[]>(300_000, 64, "official-latest-v6");
const rawCatalogSnapshot = snapshotCache<LatestOfficialPrice[]>(300_000, 1, "official-raw-catalog-v1");
const historySnapshot = snapshotCache<{ reference: OfficialPrice; history: OfficialPrice[] } | null>(300_000, 64, "official-history-v6");
const acelgaWeeklySnapshot = snapshotCache<OfficialPrice[]>(300_000, 1, "acelga-weekly-raw-v2");
const corabastosHistorySnapshot = snapshotCache<OfficialPrice[]>(300_000, 64, "weekly-corabastos-raw-v1");
const corabastosIdentitySnapshot = snapshotCache<WeeklyCorabastosGroup | null>(300_000, 64, "weekly-corabastos-identity-v1");
const minoristaWeeklySnapshot = snapshotCache<OfficialPrice[]>(300_000, 1, "minorista-weekly-raw-v1");
const aguacateBucaramangaWeeklySnapshot = snapshotCache<OfficialPrice[]>(300_000, 1, "aguacate-bucaramanga-weekly-raw-v1");
const capitalizationHistorySnapshot = snapshotCache<OfficialPrice[]>(300_000, 64, "weekly-capitalization-raw-v1");

/** Ingestion owns revision selection; request reads stay proportional to catalog size. */
export const LATEST_OFFICIAL_REFERENCES_SQL = `
  SELECT payload FROM official_catalog_current
  WHERE payload IS NOT NULL AND NOT dirty AND version='official-catalog-v1'
    AND (payload->>'observed_on')::date <= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date`;

/** Resolve each date from its ordered source revisions before fetching payloads.
 * Eligibility and milk bulletin precedence match published_official_price.
 * The ordered subquery prevents checks of every overlapping retained original;
 * a reviewed or superseded first choice falls back to the next eligible source. */
export const OFFICIAL_REFERENCE_HISTORY_SQL = `
 WITH candidates AS MATERIALIZED (
   SELECT document_id,source_locator,parser_version,quote_key,observed_on,
     parsed_at,series
   FROM official_price_quote WHERE quote_key=$1
     AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
 ), latest_parses AS MATERIALIZED (
   SELECT document_id,source_locator,max(parsed_at) AS parsed_at
   FROM candidates GROUP BY document_id,source_locator
 ), current_candidates AS MATERIALIZED (
   SELECT q.* FROM candidates q JOIN latest_parses
     USING(document_id,source_locator,parsed_at)
 ), documents AS MATERIALIZED (
   SELECT selected.document_id,d.source_url,d.retrieved_at,d.reference_period
   FROM (SELECT DISTINCT document_id FROM candidates) selected
   CROSS JOIN LATERAL (
     SELECT source_url,retrieved_at,reference_period FROM source_document
     WHERE id=selected.document_id OFFSET 0
   ) d
 ), days AS MATERIALIZED (
   SELECT DISTINCT observed_on FROM candidates
 ), winners AS MATERIALIZED (
   SELECT selected.* FROM days day CROSS JOIN LATERAL (
     SELECT ranked.document_id,ranked.source_locator,ranked.parser_version,
       ranked.observed_on,ranked.source_url
     FROM (
       SELECT q.*,d.source_url FROM current_candidates q JOIN documents d USING(document_id)
       LEFT JOIN LATERAL (
         SELECT original.details->>'bulletin_period' AS bulletin_period
         FROM official_price_quote original
         WHERE q.series='dane-milk-macroregion'
           AND original.document_id=q.document_id
           AND original.source_locator=q.source_locator
           AND original.parser_version=q.parser_version OFFSET 0
       ) milk ON TRUE
       WHERE q.observed_on=day.observed_on
       ORDER BY CASE WHEN q.series='dane-milk-macroregion'
         AND q.observed_on=(date_trunc('month',q.observed_on)+interval '1 month - 1 day')::date
         AND COALESCE(NULLIF(milk.bulletin_period,''),d.reference_period) IN (
           to_char(q.observed_on,'YYYY-MM-DD'),
           to_char(date_trunc('month',q.observed_on)+interval '2 months - 1 day','YYYY-MM-DD'))
         THEN COALESCE(NULLIF(milk.bulletin_period,''),d.reference_period)
         END DESC NULLS LAST,d.retrieved_at DESC,q.parsed_at DESC,q.source_locator OFFSET 0
     ) ranked
     WHERE NOT EXISTS(SELECT 1 FROM official_price_quote newer
       WHERE newer.document_id=ranked.document_id AND newer.source_locator=ranked.source_locator
         AND newer.parsed_at>ranked.parsed_at OFFSET 0)
       AND NOT EXISTS(SELECT 1 FROM ingestion_asset a WHERE a.document_id=ranked.document_id
         AND a.status='review' AND (a.observed_on IS NULL OR a.observed_on=ranked.observed_on) OFFSET 0)
       AND NOT EXISTS(SELECT 1 FROM official_source_review r
         WHERE r.document_id=ranked.document_id AND r.source_locator=ranked.source_locator
           AND r.created_at>=ranked.parsed_at OFFSET 0)
     LIMIT 1
   ) selected
 )
 SELECT q.*,w.source_url FROM winners w JOIN official_price_quote q
   USING(document_id,source_locator,parser_version)
 ORDER BY w.observed_on`;

// Keep the existing indexed one-key publication seek. A single five-key SQL
// candidate set scans too much retained history and exceeded the 12s deadline
// on the production reader; five one-key seeks took 1.3s in one read snapshot.
function acelgaWeeklyHistorySnapshot() {
  return acelgaWeeklySnapshot.withExpiry("five-verified-keys", async () => {
    const client = await database().connect();
    const rows: OfficialPrice[] = [];
    try {
      await client.query("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ");
      for (const key of ACELGA_WEEKLY_KEYS) {
        rows.push(...(await client.query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [key])).rows);
      }
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return rows;
  });
}

function rawOfficialCatalogSnapshot() {
  return rawCatalogSnapshot.withExpiry("all", async () =>
    (await database().query<{ payload: LatestOfficialPrice }>(LATEST_OFFICIAL_REFERENCES_SQL))
      .rows.map((row) => row.payload));
}

function capitalizationGroupHistorySnapshot(group: CapitalizationGroup, rawExpiresAt: number) {
  if (group.keys.length > MAX_WEEKLY_CAPITALIZATION_KEYS)
    throw new Error("WEEKLY_CAPITALIZATION_IDENTITY_CONFLICT");
  const membership = JSON.stringify([group.canonicalKey, [...group.keys].sort()]);
  return capitalizationHistorySnapshot.withExpiry(membership, async () => {
    const client = await database().connect();
    const rows: OfficialPrice[] = [];
    try {
      await client.query("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ");
      for (const key of group.keys)
        rows.push(...(await client.query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [key])).rows);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return rows;
  }, () => rawExpiresAt);
}

function minoristaWeeklyHistorySnapshot() {
  return minoristaWeeklySnapshot.withExpiry("two-verified-keys", async () => {
    const client = await database().connect();
    const rows: OfficialPrice[] = [];
    try {
      await client.query("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ");
      for (const key of MINORISTA_WEEKLY_KEYS)
        rows.push(...(await client.query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [key])).rows);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return rows;
  });
}

function aguacateBucaramangaWeeklyHistorySnapshot() {
  return aguacateBucaramangaWeeklySnapshot.withExpiry("two-verified-keys", async () => {
    const client = await database().connect();
    const rows: OfficialPrice[] = [];
    try {
      await client.query("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ");
      for (const key of AGUACATE_BUCARAMANGA_WEEKLY_KEYS)
        rows.push(...(await client.query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [key])).rows);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return rows;
  });
}

/** A dirty catalog payload can identify a retained key, but cannot supply a
 * price. Old bookmarks still read the authoritative, guarded quote history
 * while ingestion finishes its derived catalog refresh. These two bounded PK
 * lookups are used only when clean catalog metadata cannot resolve the group. */
function registeredCorabastosGroupSnapshot(id: string) {
  return corabastosIdentitySnapshot.withExpiry(id, async () => {
    const selected = (await database().query<{ payload: LatestOfficialPrice }>(
      "SELECT payload FROM official_catalog_current WHERE quote_key=$1 AND payload IS NOT NULL AND version='official-catalog-v1'", [id],
    )).rows[0]?.payload;
    if (!selected || expectedWeeklyCorabastosKey(selected) !== id) return null;
    const keys = [...WEEKLY_CORABASTOS_MARKETS].map((market) =>
      expectedWeeklyCorabastosKey({ ...selected, market }));
    const metadata = (await database().query<{ payload: LatestOfficialPrice }>(
      "SELECT payload FROM official_catalog_current WHERE quote_key=ANY($1::text[]) AND payload IS NOT NULL AND version='official-catalog-v1'", [keys],
    )).rows.map((row) => row.payload);
    return weeklyCorabastosGroups(metadata).byKey.get(id) || null;
  });
}

function corabastosGroupHistorySnapshot(group: WeeklyCorabastosGroup) {
  const membership = JSON.stringify([group.canonicalKey, [...group.keys].sort()]);
  return corabastosHistorySnapshot.withExpiry(membership, async () => {
    const client = await database().connect();
    const rows: OfficialPrice[] = [];
    try {
      await client.query("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ");
      for (const key of group.keys)
        rows.push(...(await client.query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [key])).rows);
      await client.query("COMMIT");
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
    return rows;
  });
}

/** Carry the exact source generation's deadline alongside its value. Reading a
 * mutable cache deadline after another source finishes could extend older data. */
export function latestOfficialReferenceSnapshot() {
  let sourceExpiresAt = Infinity;
  return latestSnapshot.withExpiry("all", async () => {
    const raw = await rawOfficialCatalogSnapshot();
    const cards = raw.value;
    sourceExpiresAt = raw.expires;
    const capitalization = capitalizationWeeklyGroups(cards).groups;
    let collapsed = collapseCapitalizationWeeklyCatalog(cards, capitalization);
    const groups = weeklyCorabastosGroups(cards).groups.filter(
      (group) => group.canonicalKey !== ACELGA_WEEKLY_CANONICAL_KEY);
    collapsed = collapseWeeklyCorabastosCatalog(collapsed, groups);
    try {
      collapsed = collapseMinoristaWeeklyCatalog(collapsed);
    } catch (error) {
      // The optional continuity bridge cannot hide a valid standalone card.
      if (!isMinoristaWeeklyConflict(error)) throw error;
    }
    try {
      collapsed = collapseAguacateBucaramangaWeeklyCatalog(collapsed);
    } catch (error) {
      // A source identity dispute cannot hide other valid official cards.
      if (!isAguacateBucaramangaWeeklyConflict(error)) throw error;
    }
    if (!cards.some((card) => isAcelgaWeeklyKey(card.quote_key)))
      return officialMarketRegions(collapsed);
    const history = await acelgaWeeklyHistorySnapshot();
    sourceExpiresAt = Math.min(sourceExpiresAt, history.expires);
    try {
      return officialMarketRegions(collapseAcelgaWeeklyCatalog(collapsed, history.value));
    } catch (error) {
      if (!isAcelgaWeeklyConflict(error)) throw error;
      return officialMarketRegions(collapsed.filter((card) => !isAcelgaWeeklyKey(card.quote_key)));
    }
  }, () => sourceExpiresAt);
}

export async function latestOfficialReferences(): Promise<LatestOfficialPrice[]> {
  return (await latestOfficialReferenceSnapshot()).value;
}

export function officialReferencesCacheExpiresAt(): number {
  return latestSnapshot.expiresAt("all");
}

export async function officialReferences(q: URLSearchParams) {
  const id = q.get("id") || "";
  if (id) {
    if (id.startsWith("summary-")) {
      const summary = await summaryReference(id);
      if (!summary) return null;
      const history = summary.history.map(normalizeOfficialLabels);
      return { reference: history.at(-1)!, history };
    }
    if (!/^[a-f0-9]{64}$/.test(id)) return null;
    const acelga = isAcelgaWeeklyKey(id);
    const minorista = isMinoristaWeeklyKey(id);
    const aguacate = isAguacateBucaramangaWeeklyKey(id);
    let group: WeeklyCorabastosGroup | undefined;
    let capitalizationGroup: CapitalizationGroup | undefined;
    let identityExpiresAt = Infinity;
    if (!acelga && !minorista && !aguacate) {
      const raw = await rawOfficialCatalogSnapshot();
      capitalizationGroup = capitalizationWeeklyGroups(raw.value).byKey.get(id);
      if (capitalizationGroup) identityExpiresAt = raw.expires;
      if (!capitalizationGroup) {
        group = weeklyCorabastosGroups(raw.value).byKey.get(id);
        if (group) identityExpiresAt = raw.expires;
        else {
          const registered = await registeredCorabastosGroupSnapshot(id);
          group = registered.value || undefined;
          identityExpiresAt = Math.min(identityExpiresAt, raw.expires, registered.expires);
        }
      }
    }
    let sourceExpiresAt = Infinity;
    const historyKey = minorista ? JSON.stringify([MINORISTA_WEEKLY_CANONICAL_KEY, id]) : aguacate
      ? JSON.stringify([AGUACATE_BUCARAMANGA_WEEKLY_CANONICAL_KEY, id]) : acelga ? ACELGA_WEEKLY_CANONICAL_KEY : capitalizationGroup
      ? JSON.stringify([capitalizationGroup.canonicalKey, [...capitalizationGroup.keys].sort()]) : group
      ? JSON.stringify([group.canonicalKey, [...group.keys].sort()]) : id;
    return historySnapshot(historyKey, async () => {
      const selected = minorista ? await minoristaWeeklyHistorySnapshot() : aguacate
        ? await aguacateBucaramangaWeeklyHistorySnapshot() : acelga ? await acelgaWeeklyHistorySnapshot() : capitalizationGroup ?
        await capitalizationGroupHistorySnapshot(capitalizationGroup, identityExpiresAt) : group ?
        await corabastosGroupHistorySnapshot(group) : {
          value: (await database().query<OfficialPrice>(OFFICIAL_REFERENCE_HISTORY_SQL, [id])).rows,
          expires: Infinity,
        };
      const rows = selected.value;
      sourceExpiresAt = Math.min(selected.expires, identityExpiresAt);
      let history: OfficialPrice[];
      try {
        history = minorista ? mergeMinoristaWeeklyHistory(rows) : aguacate
          ? mergeAguacateBucaramangaWeeklyHistory(rows) : acelga ? mergeAcelgaWeeklyHistory(rows) : capitalizationGroup ?
          mergeCapitalizationWeeklyHistory(capitalizationGroup, rows) : group ?
          mergeWeeklyCorabastosHistory(group, rows) : rows;
      } catch (error) {
        if (isMinoristaWeeklyConflict(error)) {
          try {
            history = standaloneMinoristaWeeklyHistory(rows, id);
          } catch (ownError) {
            if (!isMinoristaWeeklyConflict(ownError)) throw ownError;
            return null;
          }
        } else if (isAguacateBucaramangaWeeklyConflict(error)) {
          try {
            history = standaloneAguacateBucaramangaWeeklyHistory(rows, id);
          } catch (ownError) {
            if (!isAguacateBucaramangaWeeklyConflict(ownError)) throw ownError;
            return null;
          }
        } else {
          if (isWeeklyCapitalizationConflict(error)) throw error;
          if (!isAcelgaWeeklyConflict(error) && !isWeeklyCorabastosConflict(error)) throw error;
          return null;
        }
      }
      const located = await officialMarketRegions(history);
      const display = located.map(normalizeOfficialLabels);
      return display.length ? { reference: display.at(-1)!, history: display } : null;
    }, () => sourceExpiresAt);
  }
  const query = (q.get("q") || "").slice(0, 150),
    category = (q.get("category") || "").slice(0, 150),
    publisher = (q.get("publisher") || "").slice(0, 150),
    currency = (q.get("currency") || "").slice(0, 3),
    page = Math.floor(Math.max(0, Math.min(500, Number(q.get("page")) || 0)));
  const fold = (value: string) => value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const search = fold(query), snapshot = (await latestOfficialReferences()).map(normalizeOfficialLabels);
  const filtered = snapshot.filter((row) =>
    (!search || fold(`${officialProductSearchNames(row).join(" ")} ${sourceTerms(row.details.identity_dimensions).join(" ")} ${row.market} ${row.basis}`).includes(search)) &&
    (!category || categoryMatches(row.category, category)) &&
    (!publisher || row.publisher === publisher) &&
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
