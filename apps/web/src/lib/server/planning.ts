import "server-only";
import { SOURCE_DOCUMENT_EVIDENCE_SQL } from "./source-document-sql";
import { EVIDENCE_REVIEW_COUNT_SQL } from "./evidence-review-sql";
import { annotateCityPartialReview } from "./city-partial-review";
import { annotateReviewedCityDate } from "./reviewed-city-source-markets";
import { annotateInputSourceAmbiguity } from "../input-source-notes";
import { OFFICIAL_EVIDENCE_ROWS_SQL } from "./official-evidence-sql";
import {
  showsSupplySummaryRecords,
  SUPPLY_PERIOD_CANONICAL_VERSION_SQL,
  SUPPLY_PERIOD_SUMMARY_SQL,
  SUPPLY_PERIOD_ROWS_SQL,
} from "./supply-summary-evidence";
import { createHash } from "node:crypto";
import { setTimeout as schedulePublicationTimeout, clearTimeout as cancelPublicationTimeout } from "node:timers";
import { annotateDailyDateResolution, annotateDailySourceVariation, type ValidatedDailyDateResolution } from "./daily-date-note";
import { reconcileInputCatalog } from "./input-identities";
import {
  canonicalInputCatalogRows,
  readEquivalentInputRows,
} from "../input-identity-equivalence";
import { database, WINDOW } from "./db";
import type {
  Evidence,
  FarmData,
  Municipality,
  Weather,
  Seasonality,
} from "../planning-types";
import { fold } from "../planning-math";
import { departmentKey, departmentVariants } from "../filter-labels";
import { normalizeLabel } from "../label-normalization";
import { CURRENT_WEATHER_KEYS, HOURLY_WEATHER_KEYS, WEATHER_REFRESH_MS, hasCurrentWeather } from "../weather-data";
export async function municipalities() {
  return (
    await database().query<Municipality>(
      "SELECT * FROM municipality ORDER BY name",
    )
  ).rows;
}
export async function farmData(id: string): Promise<FarmData | null> {
  const db = database(),
    municipality = (
      await db.query<Municipality>("SELECT * FROM municipality WHERE id=$1", [
        id,
      ])
    ).rows[0];
  if (!municipality) return null;
  const [crops, calendars, suitability, soil, templates, advisories] =
    await Promise.all([
      db.query(
        "SELECT * FROM crop_reference WHERE municipality_id=$1 ORDER BY harvested_ha DESC,crop,variety",
        [id],
      ),
      db.query(
        "SELECT * FROM crop_calendar WHERE department_id=$1 ORDER BY crop,activity",
        [municipality.department_id],
      ),
      db.query(
        `SELECT s.*,d.title,jsonb_build_object('scale',d.metadata->>'scale') AS metadata FROM crop_suitability s JOIN source_document d ON d.id=s.document_id WHERE municipality_id=$1 ORDER BY s.crop_key,s.classification`,
        [id],
      ),
      db.query("SELECT * FROM soil_reference WHERE municipality_id=$1", [id]),
      db.query(
        "SELECT * FROM cost_template ORDER BY CASE WHEN municipalities ? $1 THEN 0 ELSE 1 END,reference_year DESC,title",
        [id],
      ),
      db.query(
        "SELECT * FROM advisory WHERE published_on<=((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date) AND (valid_until IS NULL OR valid_until>=((CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date)) ORDER BY published_on DESC",
      ),
    ]);
  return {
    municipality,
    crops: crops.rows,
    calendars: calendars.rows,
    suitability: suitability.rows,
    soil: soil.rows[0] || null,
    templates: templates.rows,
    advisories: advisories.rows.filter(
      (a) =>
        !a.departments.length ||
        a.departments.some(
          (d: string) => fold(d) === fold(municipality.department),
        ),
    ),
  };
}
export async function seasonality(
  product: string,
  market: string,
): Promise<Seasonality> {
  const db = database(),
    coffee = product === "cafe-pergamino-seco";
  const [latest, years] = await Promise.all([
    coffee
      ? db.query(
          `SELECT price/125 AS price, observed_on AS date,'FNC nacional' AS market FROM coffee_reference WHERE ${WINDOW} ORDER BY observed_on DESC LIMIT 1`,
        )
      : db.query(
          `SELECT o.price,o.unit,o.observed_on AS date,m.name AS market FROM published_price_observation o JOIN market m ON m.id=o.market_id WHERE product_id=$1 AND market_id=$2 AND o.unit='kg' AND o.period='monthly' AND ${WINDOW} ORDER BY observed_on DESC LIMIT 1`,
          [product, market],
        ),
    db.query(
      "SELECT reference_year,monthly_prices,document_id,source_rows,source_documents FROM seasonal_year WHERE validation_version='seasonality-kg-v2' AND review_reason IS NULL AND product_id=$1 AND market_id=$2 AND reference_year BETWEEN EXTRACT(YEAR FROM CURRENT_DATE)-5 AND EXTRACT(YEAR FROM CURRENT_DATE)-1 ORDER BY reference_year",
      [product, coffee ? "fnc-national" : market],
    ),
  ]);
  return {
    latest: latest.rows[0] ? { ...latest.rows[0],
      market: normalizeLabel(latest.rows[0].market, "place") } : null,
    years: years.rows,
    unit: coffee ? "kg de pergamino seco" : latest.rows[0]?.unit || "kg",
    method:
      "Para cada año completo se divide el precio de cada mes por el promedio de sus 12 precios mensuales y se multiplica por 100. El gráfico muestra la mediana de esos índices para cada mes, en el mismo producto y mercado. Se requieren al menos 3 años completos y comparables. Los precios de la tabla son nominales, sin ajuste por inflación. El patrón describe la historia; no calcula precios futuros ni recomienda un mes de venta.",
  };
}
/** Catalog reads select a winner before loading its previous-month price.
 * Detail reads retain a separate newest quote for every exact location.
 */
type InputPublication = {
  examined: Set<string>;
  winners: Map<string, Record<string, unknown>>;
  revision: string | undefined;
};
const inputPublications = new Map<string, {
  expires: number; result: Promise<InputPublication>;
}>();

async function inputPublicationRevision(scope: string): Promise<string | undefined> {
  try {
    // Raw writes and exact supersessions advance the source epoch. The two
    // append-only relations can change publication without a physical price
    // write, so their insert counts also belong to this revision token.
    const row = (await withHistoricalCatalogSlot(() => database().query(`
      SELECT s.source_epoch::text AS source_epoch,
        (SELECT count(*)::text FROM input_identity_alias) AS alias_count,
        (SELECT count(*)::text FROM ingestion_checkpoint
          WHERE step='inputs-pdf:published'
            AND processor_version ~ '^inputs-pdf-v[0-9]+$') AS checkpoint_count
      FROM input_latest_projection_state s WHERE s.scope=$1`, [scope]))).rows[0];
    return row && [row.source_epoch, row.alias_count, row.checkpoint_count]
      .every((value) => typeof value === "string" && /^\d+$/.test(value))
      ? JSON.stringify([row.source_epoch, row.alias_count, row.checkpoint_count]) : undefined;
  } catch (error) {
    // An old installation without the projection metadata retains the exact
    // unshared SQL path. Missing evidence must never imply publication absence.
    if (!["42P01", "42703", "55000"].includes((error as { code?: string }).code || "")) throw error;
    return undefined;
  }
}

async function inputPublicationWithinBudget(result: Promise<InputPublication>) {
  let timer: ReturnType<typeof schedulePublicationTimeout> | undefined;
  try {
    return await Promise.race([
      result.catch(() => undefined),
      new Promise<undefined>((resolve) => {
        timer = schedulePublicationTimeout(() => resolve(undefined), 15_000);
      }),
    ]);
  } finally {
    if (timer) cancelPublicationTimeout(timer);
  }
}

/** Share authoritative exception reads across concurrent geographic catalogs.
 * An absent national winner proves absence in every department; a winner in
 * another department never substitutes for the requested regional winner.
 */
async function readInputRows(
  department: string, scope = "department", historical = false, id = "", grouped = false,
) {
  if (!grouped || id)
    return readInputRowsUnshared(department, scope, historical, id, grouped);
  for (const [key, entry] of inputPublications)
    if (entry.expires <= Date.now()) inputPublications.delete(key);
  const day = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
  const key = JSON.stringify([scope === "municipality" ? scope : "department", historical, day]);
  const shared = inputPublications.get(key);
  if (department)
    return readInputRowsUnshared(department, scope, historical, id, grouped,
      undefined, shared && shared.expires > Date.now() ? shared.result : undefined);
  let publish!: (value: InputPublication) => void;
  let reject!: (reason: unknown) => void;
  const result = new Promise<InputPublication>((resolve, fail) => { publish = resolve; reject = fail; });
  // A national request can fail before a regional subscriber exists.
  void result.catch(() => undefined);
  const entry = { expires: Date.now() + 300_000, result };
  if (!inputPublications.has(key) && inputPublications.size >= 8)
    inputPublications.delete(inputPublications.keys().next().value!);
  inputPublications.set(key, entry);
  try {
    return await readInputRowsUnshared(department, scope, historical, id, grouped,
      (examined, rows, revision) => publish({ examined: new Set(examined), revision,
        winners: new Map(rows.map((row) => [String(row.id), row])) }));
  } catch (error) {
    reject(error);
    if (inputPublications.get(key) === entry) inputPublications.delete(key);
    throw error;
  }
}

async function readInputRowsUnshared(
  department: string,
  scope = "department",
  historical = false,
  id = "",
  grouped = false,
  publish?: (examined: string[], rows: Record<string, unknown>[], revision?: string) => void,
  shared?: Promise<InputPublication>,
) {
  const municipal = scope === "municipality";
  const departments = departmentVariants(department);
  const table = municipal ? "input_municipal_price" : "input_price";
  const period = historical ? "observed_on<=CURRENT_DATE" : WINDOW;
  const locationKeys = grouped
    ? ""
    : `,department${municipal ? ",municipality" : ""}`;
  // A national catalog touches thousands of identities. Select only identities
  // in its requested period, then keep each current/prior-price read bounded;
  // the complete result and failures still share the existing catalog cache.
  const batchedCatalog = grouped && !department && !id;
  if (grouped && !id) {
    // A grouped DISTINCT over the published view checks every retained
    // revision, even for one department. Seek one raw latest row per identity
    // instead, and send only
    // identities that can be affected by a PDF withdrawal or alias through
    // the exact published view. Neither branch discards a historical identity.
    const projection = municipal ? "input_municipal_latest_raw" : "input_department_latest_raw";
    // For a named department, find its newest date using the location key
    // index first. A date-ordered national payload seek otherwise scans years
    // of other locations when an identity has no quote in this department.
    // GROUP BY retains the regional aggregate instead of a global min/max seek.
    const departmentDateSql = (id: string, parameter: number) => department
      ? `AND p.observed_on=(
          SELECT max(latest.observed_on) FROM ${table} latest
          WHERE latest.id=${id} AND latest.department=ANY($${parameter}::text[])
            AND ${period.replaceAll("observed_on", "latest.observed_on")}
          GROUP BY latest.id
        )`
      : "";
    const readProjection = async (lower: string, upper: string) => {
      const args: unknown[] = [municipal ? "municipality" : "department"];
      if (department) args.push(departments);
      const lowerParameter = lower ? args.push(lower) : 0;
      const upperParameter = upper ? args.push(upper) : 0;
      const bound = (column: string) =>
        `${lowerParameter ? `AND ${column}>=$${lowerParameter}` : ""}
         ${upperParameter ? `AND ${column}<$${upperParameter}` : ""}`;
      const sql = `WITH state AS MATERIALIZED (
        SELECT projection_epoch,
          (projection_epoch=source_epoch AND
            asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date) AS fresh,
          (delta_complete AND
            asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date) AS delta_ready
        FROM input_latest_projection_state WHERE scope=$1
      ) SELECT (s.fresh OR s.delta_ready) AS ready,x.* FROM state s LEFT JOIN LATERAL (
        WITH delta_ids AS MATERIALIZED (
        SELECT d.id FROM input_latest_projection_delta d
        WHERE s.delta_ready AND NOT s.fresh AND d.scope=$1
          AND d.changed_epoch>s.projection_epoch ${bound("d.id")}
      ), pointers AS MATERIALIZED (
        SELECT DISTINCT ON (l.id) l.id,l.department${municipal ? ",l.municipality" : ""},l.observed_on
        FROM ${projection} l WHERE (s.fresh OR s.delta_ready)
          ${bound("l.id")}
          AND NOT EXISTS (SELECT 1 FROM delta_ids d WHERE d.id=l.id)
          AND ${period.replaceAll("observed_on", "l.observed_on")}
          ${department ? "AND l.department=ANY($2::text[])" : ""}
        ORDER BY l.id,l.observed_on DESC,l.price,l.department${municipal ? ",l.municipality" : ""}
      ), selected AS MATERIALIZED (
        SELECT p.* FROM pointers l JOIN ${projection} p
          ON p.id=l.id AND p.department=l.department
          ${municipal ? "AND p.municipality=l.municipality" : ""}
          AND p.observed_on=l.observed_on
        UNION ALL
        SELECT p.id,p.department${municipal ? ",p.municipality" : ""},p.observed_on,
          p.price,p.name,p.category,p.presentation,p.document_id,
          p.source_locator,p.brand,p.registration,p.product_line
        FROM delta_ids d CROSS JOIN LATERAL (
          SELECT p.* FROM ${table} p WHERE p.id=d.id
            AND ${period.replaceAll("observed_on", "p.observed_on")}
            ${department ? "AND p.department=ANY($2::text[])" : ""}
            ${departmentDateSql("d.id", 2)}
          ORDER BY p.observed_on DESC,p.price,p.department${municipal ? ",p.municipality" : ""}
          LIMIT 1
        ) p
      ), withdrawn AS MATERIALIZED (
        SELECT c.document_id,max(substring(c.processor_version from '([0-9]+)$')::numeric) AS version
        FROM ingestion_checkpoint c JOIN (
          SELECT DISTINCT document_id FROM selected
        ) documents ON documents.document_id=c.document_id
        WHERE c.step='inputs-pdf:published'
          AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
        GROUP BY c.document_id
      ), aliased AS MATERIALIZED (
        SELECT DISTINCT legacy_id AS id FROM input_identity_alias
      ) SELECT p.*${municipal ? "" : ",''::text AS municipality"},
        (a.id IS NOT NULL OR coalesce(w.version >
          coalesce(substring(p.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false)
        ) AS needs_published_lookup
      FROM selected p
      LEFT JOIN withdrawn w ON w.document_id=p.document_id
      LEFT JOIN aliased a ON a.id=p.id
      ) x ON (s.fresh OR s.delta_ready) ORDER BY x.id`;
      try {
        const rows = (await withHistoricalCatalogSlot(() =>
          database().query(sql, args))).rows;
        return { ready: rows[0]?.ready === true,
          rows: rows.filter((row) => row.id !== null).map(({ ready: _ready, ...row }) => row) };
      } catch (error) {
        if (!["42P01", "42703", "55000"].includes((error as { code?: string }).code || "")) throw error;
        return { ready: false, rows: [] };
      }
    };
    const readRange = async (lower: string, upper: string) => {
      const bound = (column: string) => `${lower ? `AND ${column}>='${lower}'` : ""}
        ${upper ? `AND ${column}<'${upper}'` : ""}`;
      const historicalQuery = `WITH RECURSIVE keys(id) AS (
        (SELECT id FROM ${table} WHERE ${period} ${department ? "AND department=ANY($1::text[])" : ""}
          ${bound("id")}
          ORDER BY id LIMIT 1)
        UNION ALL
        SELECT next.id FROM keys k CROSS JOIN LATERAL (
          SELECT id FROM ${table} WHERE id>k.id AND ${period}
            ${department ? "AND department=ANY($1::text[])" : ""}
            ${bound("id")}
          ORDER BY id LIMIT 1
        ) next
      ), raw_winners AS MATERIALIZED (
        SELECT p.* FROM keys k CROSS JOIN LATERAL (
          SELECT p.* FROM ${table} p WHERE p.id=k.id AND ${period.replaceAll("observed_on", "p.observed_on")}
            ${department ? "AND p.department=ANY($1::text[])" : ""}
            ${departmentDateSql("k.id", 1)}
            ${bound("p.id")}
          ORDER BY p.observed_on DESC,p.price,p.department${municipal ? ",p.municipality" : ""} LIMIT 1
        ) p
      ), withdrawn AS MATERIALIZED (
        SELECT c.document_id,max(substring(c.processor_version from '([0-9]+)$')::numeric) AS version
        FROM ingestion_checkpoint c JOIN (
          SELECT DISTINCT document_id FROM raw_winners
        ) documents ON documents.document_id=c.document_id
        WHERE c.step='inputs-pdf:published'
          AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
        GROUP BY c.document_id
      ), aliased AS MATERIALIZED (
        SELECT DISTINCT legacy_id AS id FROM input_identity_alias
      ), flags AS MATERIALIZED (
        SELECT r.id,(a.id IS NOT NULL OR
          coalesce(s.version>coalesce(substring(r.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false)
        ) AS needs_published_lookup
        FROM raw_winners r LEFT JOIN withdrawn s ON s.document_id=r.document_id
        LEFT JOIN aliased a ON a.id=r.id
      )
      SELECT r.*${municipal ? "" : ",''::text AS municipality"},
        f.needs_published_lookup
      FROM raw_winners r JOIN flags f USING(id) ORDER BY r.id`;
      return (await withHistoricalCatalogSlot(() =>
        database().query(historicalQuery, department ? [departments] : []))).rows;
    };
    // Contiguous lexical ranges retain every ID while bounding each indexed
    // walk during ingestion. Named departments use the same bounded reads.
    const bounds = ["", "c", "e", "g", "j", "m", "p", "s", "v", ""];
    const ranges = bounds.slice(0, -1).map((lower, index) => [lower, bounds[index + 1]]);
    const raw = [];
    // Fair per-statement slots let a named department read between national
    // ranges and leave pool capacity for product and official-source screens.
    // The small pointer relation still spans tens of thousands of locations.
    // Read its delta overlay in the same exhaustive ranges as the raw fallback,
    // so simultaneous national catalogs do not need one large sort/lookup burst.
    // Each range checks its epoch/day and falls back independently if needed.
    for (const [lower, upper] of ranges) {
      const projected = await readProjection(lower, upper);
      if (projected.ready) raw.push(...projected.rows);
      else raw.push(...await readRange(lower, upper));
    }
    let exceptionIds = raw.filter((row) => row.needs_published_lookup).map((row) => row.id);
    const revisionBefore = publish && exceptionIds.length
      ? await inputPublicationRevision(municipal ? "municipality" : "department") : undefined;
    // The published view applies two exact eligibility rules. Evaluating it
    // once per legacy alias walks years of source rows and repeats replacement
    // probes under write load. Materialize the bounded candidates and both
    // rules as sets, then choose the same latest eligible winner per ID.
    // The projected current row tells us exactly which identities need the
    // authoritative publication view. Seeking only those IDs lets the view
    // apply its withdrawal and alias rules before choosing the latest winner;
    // materializing every historical candidate and replacement for each
    // exception repeated years of I/O during a concurrent writer.
    const exceptionQuery = `SELECT p.*${municipal ? "" : ",''::text AS municipality"}
      FROM unnest($1::text[]) AS keys(id) CROSS JOIN LATERAL (
        SELECT p.* FROM published_${table} p WHERE p.id=keys.id
          AND ${period.replaceAll("observed_on", "p.observed_on")}
          ${department ? "AND p.department=ANY($2::text[])" : ""}
        ORDER BY p.observed_on DESC,p.price,p.department${municipal ? ",p.municipality" : ""}
        LIMIT 1
      ) p ORDER BY p.id`;
    const exceptions = [];
    if (shared && exceptionIds.length) {
      // Wait outside the SQL-slot queue. A failed national read supplies no
      // evidence; this regional request still performs its own exact lookup.
      const published = await inputPublicationWithinBudget(shared);
      const revisionNow = published?.revision
        ? await inputPublicationRevision(municipal ? "municipality" : "department") : undefined;
      if (published?.revision && published.revision === revisionNow) exceptionIds = exceptionIds.filter((id) => {
        if (!published.examined.has(id)) return true;
        const winner = published.winners.get(id);
        if (!winner) return false;
        if (!departments.includes(String(winner.department))) return true;
        exceptions.push(winner);
        return false;
      });
    }
    for (let offset = 0; offset < exceptionIds.length; offset += 40) {
      exceptions.push(...(await withHistoricalCatalogSlot(() =>
        database().query(exceptionQuery,
          department ? [exceptionIds.slice(offset, offset + 40), departments]
            : [exceptionIds.slice(offset, offset + 40)]))).rows);
    }
    if (publish) {
      const revisionAfter = revisionBefore
        ? await inputPublicationRevision(municipal ? "municipality" : "department") : undefined;
      publish(exceptionIds, exceptions,
        revisionBefore && revisionBefore === revisionAfter ? revisionAfter : undefined);
    }
    const rows = raw.filter((row) => !row.needs_published_lookup)
      .map(({ needs_published_lookup: _ignored, ...row }) => row)
      .concat(exceptions)
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((row) => ({ ...row, scope: municipal ? "municipality" : "department" }));
    if (!rows.length) return rows;
    // The current-winner and previous-month reads have separate 15-second SQL
    // budgets; a single national statement otherwise times out after doing
    // both indexed walks. The previous candidates retain the exact winner's
    // location and only exceptional revisions use the published view.
    const previousQuery = `WITH winners AS MATERIALIZED (
        SELECT * FROM jsonb_to_recordset($1::jsonb)
          AS w(id text,department text,municipality text,observed_on date)
      ), previous_raw AS MATERIALIZED (
        SELECT w.*,p.price,p.observed_on AS previous_date,p.document_id,p.source_locator
        FROM winners w LEFT JOIN LATERAL (
          SELECT p.price,p.observed_on,p.document_id,p.source_locator FROM ${table} p
          WHERE p.id=w.id AND p.department=w.department ${municipal ? "AND p.municipality=w.municipality" : ""}
            AND p.observed_on>=(date_trunc('month',w.observed_on)-interval '1 month')::date
            AND p.observed_on<date_trunc('month',w.observed_on)::date
            AND ${period.replaceAll("observed_on", "p.observed_on")}
          ORDER BY p.observed_on DESC LIMIT 1
        ) p ON TRUE
      ), withdrawn AS MATERIALIZED (
        SELECT c.document_id,max(substring(c.processor_version from '([0-9]+)$')::numeric) AS version
        FROM ingestion_checkpoint c JOIN (
          SELECT DISTINCT document_id FROM previous_raw WHERE document_id IS NOT NULL
        ) documents ON documents.document_id=c.document_id
        WHERE c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
        GROUP BY c.document_id
      ), aliased AS MATERIALIZED (
        SELECT DISTINCT legacy_id AS id FROM input_identity_alias
      )
      SELECT previous_raw.id,
        CASE WHEN a.id IS NOT NULL OR coalesce(s.version>
          coalesce(substring(previous_raw.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false)
          THEN previous_verified.price ELSE previous_raw.price END AS previous_price,
        CASE WHEN a.id IS NOT NULL OR coalesce(s.version>
          coalesce(substring(previous_raw.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false)
          THEN previous_verified.observed_on ELSE previous_raw.previous_date END AS previous_date
      FROM previous_raw
      LEFT JOIN withdrawn s ON s.document_id=previous_raw.document_id
      LEFT JOIN aliased a ON a.id=previous_raw.id
      LEFT JOIN LATERAL (
        SELECT p.price,p.observed_on FROM published_${table} p
        WHERE (a.id IS NOT NULL OR coalesce(s.version>
            coalesce(substring(previous_raw.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false))
          AND p.id=previous_raw.id AND p.department=previous_raw.department ${municipal ? "AND p.municipality=previous_raw.municipality" : ""}
          AND p.observed_on>=(date_trunc('month',previous_raw.observed_on)-interval '1 month')::date
          AND p.observed_on<date_trunc('month',previous_raw.observed_on)::date
          AND ${period.replaceAll("observed_on", "p.observed_on")}
        ORDER BY p.observed_on DESC LIMIT 1
      ) previous_verified ON TRUE ORDER BY previous_raw.id`;
    const keys = rows.map((row) => ({ id: row.id, department: row.department,
      municipality: row.municipality, observed_on: row.observed_on }));
    const previous = [];
    for (let offset = 0; offset < keys.length; offset += 500) {
      previous.push(...(await withHistoricalCatalogSlot(() =>
        database().query(previousQuery,
          [JSON.stringify(keys.slice(offset, offset + 500))]))).rows);
    }
    const byId = new Map(previous.map((row) => [row.id, row]));
    return rows.map((row) => ({ ...row, previous_price: byId.get(row.id)?.previous_price ?? null,
      previous_date: byId.get(row.id)?.previous_date ?? null }));
  }
  if (id && historical && !grouped) {
    // A detail can span over a hundred locations. The published view's
    // per-location latest seek otherwise checks every older physical row at
    // every location. Find each raw location winner once; only a withdrawn PDF
    // revision or legacy alias needs the exact published-view fallback.
    const location = municipal ? "department,municipality" : "department";
    const rawQuery = `WITH raw AS MATERIALIZED (
        SELECT DISTINCT ON (${location}) p.* FROM ${table} p
        WHERE p.id=$1 AND p.observed_on<=CURRENT_DATE AND (cardinality($2::text[])=0 OR p.department=ANY($2::text[]))
        ORDER BY ${location},observed_on DESC,price
      ), withdrawn AS MATERIALIZED (
        SELECT c.document_id,max(substring(c.processor_version from '([0-9]+)$')::numeric) AS version
        FROM ingestion_checkpoint c JOIN (SELECT DISTINCT document_id FROM raw) d USING(document_id)
        WHERE c.step='inputs-pdf:published' AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
        GROUP BY c.document_id
      ), aliased AS (
        SELECT EXISTS(SELECT 1 FROM input_identity_alias WHERE legacy_id=$1) AS yes
      )
      SELECT r.*${municipal ? "" : ",''::text AS municipality"},
        (a.yes OR coalesce(s.version>
          coalesce(substring(r.source_locator from '; inputs-pdf-v([0-9]+)$')::numeric,0),false)
        ) AS needs_published_lookup
      FROM raw r LEFT JOIN withdrawn s USING(document_id) CROSS JOIN aliased a`;
    const raw = (await database().query(rawQuery, [id, departments])).rows;
    const flagged = raw.filter((row) => row.needs_published_lookup);
    const publishedTable = `published_${table}`;
    const fallbackQuery = `SELECT DISTINCT ON (${location}) p.*${municipal ? "" : ",''::text AS municipality"}
      FROM ${publishedTable} p JOIN jsonb_to_recordset($2::jsonb)
        AS f(department text,municipality text)
        ON p.department=f.department ${municipal ? "AND p.municipality=f.municipality" : ""}
      WHERE p.id=$1 AND p.observed_on<=CURRENT_DATE
      ORDER BY ${location},p.observed_on DESC,p.price`;
    const fallback = flagged.length ? (await database().query(fallbackQuery, [id,
      JSON.stringify(flagged.map((row) => ({ department: row.department,
        municipality: row.municipality })))] )).rows : [];
    const winners = raw.filter((row) => !row.needs_published_lookup)
      .map(({ needs_published_lookup: _ignored, ...row }) => row).concat(fallback);
    if (!winners.length) return winners;
    const previousQuery = `WITH winners AS MATERIALIZED (
        SELECT * FROM jsonb_to_recordset($1::jsonb) AS w(
          id text,department text,observed_on date,name text,category text,
          presentation text,price numeric,document_id text,source_locator text,
          brand text,registration text,product_line text,municipality text)
      ) SELECT w.*,'${municipal ? "municipality" : "department"}'::text AS scope,
        previous.price AS previous_price,previous.observed_on AS previous_date
      FROM winners w LEFT JOIN LATERAL (
        SELECT p.price,p.observed_on FROM ${publishedTable} p
        WHERE p.id=w.id AND p.department=w.department
          ${municipal ? "AND p.municipality=w.municipality" : ""}
          AND p.observed_on>=(date_trunc('month',w.observed_on)-interval '1 month')::date
          AND p.observed_on<date_trunc('month',w.observed_on)::date
          AND p.observed_on<=CURRENT_DATE
        ORDER BY p.observed_on DESC LIMIT 1
      ) previous ON TRUE
      ORDER BY w.category,w.name,w.presentation,w.department,w.municipality`;
    return (await database().query(previousQuery, [JSON.stringify(winners)])).rows;
  }
  const identityQuery = batchedCatalog ? `identities AS MATERIALIZED (
      SELECT id,CURRENT_DATE AS latest_date FROM unnest($3::text[]) AS selected(id) WHERE ($2='' OR id=$2)
    ` : `identities AS MATERIALIZED (
      SELECT id${locationKeys},max(observed_on) AS latest_date FROM ${table}
      WHERE ${period} AND (cardinality($1::text[])=0 OR department=ANY($1::text[])) AND ($2='' OR id=$2)
      GROUP BY id${locationKeys} ORDER BY id${locationKeys}
    `;
  const query = `WITH ${identityQuery}    ), winners AS MATERIALIZED (
      SELECT p.*${municipal ? "" : ",''::text AS municipality"} FROM identities i
      CROSS JOIN LATERAL (
        SELECT p.* FROM published_${table} p WHERE p.id=i.id AND p.observed_on<=i.latest_date
          AND ${period} AND (cardinality($1::text[])=0 OR p.department=ANY($1::text[]))
          ${grouped ? "" : `AND p.department=i.department ${municipal ? "AND p.municipality=i.municipality" : ""}`}
        ORDER BY p.observed_on DESC,p.price,p.department${municipal ? ",p.municipality" : ""} LIMIT 1
      ) p
    )
    SELECT w.*, '${municipal ? "municipality" : "department"}'::text AS scope,
      previous.price AS previous_price,previous.observed_on AS previous_date
    FROM winners w LEFT JOIN LATERAL (
      SELECT p.price,p.observed_on FROM published_${table} p
      WHERE p.id=w.id AND p.department=w.department ${municipal ? "AND p.municipality=w.municipality" : ""}
        AND p.observed_on>=(date_trunc('month',w.observed_on)-interval '1 month')::date
        AND p.observed_on<date_trunc('month',w.observed_on)::date AND ${period}
      ORDER BY p.observed_on DESC LIMIT 1
    ) previous ON TRUE
    ORDER BY ${grouped ? "w.id" : "w.category,w.name,w.presentation,w.department,w.municipality"}`;
  if (batchedCatalog) {
    const keys = (await database().query<{ id: string }>(
      `SELECT id FROM ${table} WHERE ${period} GROUP BY id ORDER BY id`,
    )).rows.map((row) => row.id);
    const rows = [];
    const batches = [];
    for (let offset = 0; offset < keys.length; offset += 250)
      batches.push(keys.slice(offset, offset + 250));
    // The published view checks original revisions and aliases for each
    // identity. Serial small batches avoid contending with the ingest worker.
    for (const batch of batches) {
      rows.push(...(await database().query(query, [departments, id, batch])).rows);
    }
    return rows;
  }
  return (await database().query(query, [departments, id])).rows;
}

/** Read original revision metadata once for the bounded result set. Direct legacy
 * detail URLs preserve their retained historical identity and remain accessible. */
async function loadInputs(department: string, scope = "department", historical = false, id = "", grouped = false) {
  const rows = id
    ? await readEquivalentInputRows(id, async (memberIds) =>
        (await Promise.all(memberIds.map((memberId) =>
          readInputRowsUnshared(department, scope, historical, memberId, grouped),
        ))).flat(),
      )
    : await readInputRows(department, scope, historical, id, grouped);
  if (id) return rows;
  return canonicalInputCatalogRows(await reconcileInputCatalog(rows));
}

// Match the catalog endpoint's five-minute freshness contract and share work
// across concurrent screens. Individual input/location reads remain uncached.
const inputCatalogCache = new Map<
  string,
  { expires: number; result: ReturnType<typeof loadInputs> }
>();
let historicalCatalogReaders = 0;
const historicalCatalogWaiters: Array<() => void> = [];
async function withHistoricalCatalogSlot<T>(read: () => Promise<T>): Promise<T> {
  if (historicalCatalogReaders >= 2)
    await new Promise<void>((resume) => historicalCatalogWaiters.push(resume));
  else historicalCatalogReaders++;
  try {
    return await read();
  } finally {
    const next = historicalCatalogWaiters.shift();
    if (next) next();
    else historicalCatalogReaders--;
  }
}
export function inputs(
  department: string,
  scope = "department",
  historical = false,
  id = "",
  grouped = false,
) {
  if (!grouped) return loadInputs(department, scope, historical, id, grouped);
  const key = JSON.stringify([departmentKey(department), scope, historical, id, grouped]);
  const cached = inputCatalogCache.get(key);
  if (cached && cached.expires > Date.now()) return cached.result;
  if (cached) inputCatalogCache.delete(key);
  if (inputCatalogCache.size >= 8)
    inputCatalogCache.delete(inputCatalogCache.keys().next().value!);
  const result = loadInputs(department, scope, historical, id, grouped);
  inputCatalogCache.set(key, { expires: Date.now() + 300_000, result });
  void result.catch((error) => {
    console.error("Input catalog read failed", error?.name || "unknown", error?.code || "unknown");
    if (inputCatalogCache.get(key)?.result === result)
      inputCatalogCache.delete(key);
  });
  return result;
}

const WEATHER_KEYS = [
  "weather_code",
  "temperature_2m_max",
  "temperature_2m_min",
  "precipitation_sum",
  "precipitation_probability_max",
  "wind_speed_10m_max",
  "et0_fao_evapotranspiration",
];
const inflight = new Map<string, Promise<Weather>>();
export async function weatherFor(lat: number, lon: number): Promise<Weather> {
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon) ||
    lat < -5 ||
    lat > 14 ||
    lon < -82 ||
    lon > -66
  )
    throw new Error("INVALID_LOCATION");
  lat = Math.round(lat * 1_000_000) / 1_000_000;
  lon = Math.round(lon * 1_000_000) / 1_000_000;
  const key = `${lat},${lon}`;
  if (inflight.has(key)) return inflight.get(key)!;
  const task = loadWeather(lat, lon);
  inflight.set(key, task);
  try {
    return await task;
  } finally {
    inflight.delete(key);
  }
}
async function loadWeather(lat: number, lon: number): Promise<Weather> {
  const db = database(),
    stored = (
      await db.query<Weather>(
        "SELECT * FROM weather_snapshot WHERE latitude=$1 AND longitude=$2 ORDER BY fetched_at DESC LIMIT 1",
        [lat, lon],
      )
    ).rows[0];
  if (stored && hasCurrentWeather(stored.payload) && Date.now() - new Date(stored.fetched_at).getTime() < WEATHER_REFRESH_MS)
    return { ...stored, stale: false };
  const apiKey = process.env.OPEN_METEO_API_KEY;
  const url = new URL(
    apiKey
      ? "https://customer-api.open-meteo.com/v1/forecast"
      : "https://api.open-meteo.com/v1/forecast",
  );
  url.search = new URLSearchParams({
    latitude: String(lat),
    longitude: String(lon),
    daily: WEATHER_KEYS.join(","),
    current: CURRENT_WEATHER_KEYS.join(","),
    hourly: HOURLY_WEATHER_KEYS.join(","),
    timezone: "America/Bogota",
    forecast_days: "7",
    temperature_unit: "celsius",
    wind_speed_unit: "kmh",
    precipitation_unit: "mm",
  }).toString();
  const publicURL = url.toString();
  if (apiKey) url.searchParams.set("apikey", apiKey);
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(12000),
      cache: "no-store",
    });
    if (!response.ok) throw new Error("WEATHER_UNAVAILABLE");
    const raw = await response.text();
    if (raw.length > 65536) throw new Error("WEATHER_SCHEMA");
    const payload = JSON.parse(raw),
      daily = payload.daily;
    if (
      !hasCurrentWeather(payload) ||
      !daily ||
      !Array.isArray(daily.time) ||
      daily.time.length !== 7 ||
      WEATHER_KEYS.some(
        (k) =>
          !Array.isArray(daily[k]) ||
          daily[k].length !== 7 ||
          daily[k].some(
            (v: unknown) =>
              v !== null && (typeof v !== "number" || !Number.isFinite(v)),
          ),
      )
    )
      throw new Error("WEATHER_SCHEMA");
    const fetched_at = new Date().toISOString(),
      id = createHash("sha256")
        .update(publicURL + "\n" + fetched_at + "\n" + JSON.stringify(payload))
        .digest("hex");
    await db.query(
      "INSERT INTO weather_snapshot(id,latitude,longitude,fetched_at,source_url,payload) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(id) DO NOTHING",
      [id, lat, lon, fetched_at, publicURL, payload],
    );
    return {
      id,
      latitude: lat,
      longitude: lon,
      fetched_at,
      source_url: publicURL,
      payload,
      stale: false,
    };
  } catch {
    if (stored && Date.now() - new Date(stored.fetched_at).getTime() < 24 * 3600000)
      return { ...stored, stale: true };
    throw new Error("WEATHER_UNAVAILABLE");
  }
}
export async function evidence(
  id: string,
  filters: URLSearchParams,
): Promise<Evidence | null> {
  const db = database();
  if (id.startsWith("weather-")) {
    const r = (
      await db.query<Weather>("SELECT * FROM weather_snapshot WHERE id=$1", [
        id.slice(8),
      ])
    ).rows[0];
    if (!r) return null;
    return {
      id,
      title: "Tiempo y pronóstico consultados - Open-Meteo",
      publisher: "Open-Meteo",
      source_url: r.source_url,
      media_type: "application/json",
      kind: "original",
      reference_period: `${r.payload.daily.time[0]} a ${r.payload.daily.time.at(-1)}`,
      retrieved_at: r.fetched_at,
      page_count: null,
      bytes: JSON.stringify(r.payload).length,
      metadata: {
        note: "Respuesta meteorológica del modelo guardada en Azure. Sus coordenadas pueden diferir del punto solicitado. El archivo descargable contiene la respuesta original completa, incluidas condiciones actuales y pronóstico por hora cuando están disponibles.",
        requested_latitude: r.latitude,
        requested_longitude: r.longitude,
        model_latitude: r.payload.latitude,
        model_longitude: r.payload.longitude,
        current: r.payload.current || null,
        current_units: r.payload.current_units || null,
        hourly_units: r.payload.hourly_units || null,
        timezone: r.payload.timezone || "America/Bogota",
      },
      parents: [],
      records: r.payload.daily.time.map((day, i) => ({
        fecha: day,
        lluvia_mm: r.payload.daily.precipitation_sum[i],
        probabilidad_por_ciento:
          r.payload.daily.precipitation_probability_max[i],
        maxima_C: r.payload.daily.temperature_2m_max[i],
        minima_C: r.payload.daily.temperature_2m_min[i],
        viento_kmh: r.payload.daily.wind_speed_10m_max[i],
        ET0_mm: r.payload.daily.et0_fao_evapotranspiration[i],
      })),
    };
  }
  const r = (
    await db.query<Evidence>(
      SOURCE_DOCUMENT_EVIDENCE_SQL,
      [id],
    )
  ).rows[0];
  if (!r) return null;
  if (r.media_type === "application/pdf") {
    const conflict = (await db.query<{ held: boolean }>(
      "SELECT EXISTS (SELECT 1 FROM unresolved_city_pdf_publication_conflict WHERE document_id=$1) AS held",
      [r.id],
    )).rows[0]?.held;
    if (conflict) {
      r.metadata.city_pdf_publication_note = "La extracción de este informe por ciudad presenta diferencias con el PDF original y está pendiente de verificación. Sus precios no se muestran en la aplicación mientras se revisan. Puedes consultar y descargar el archivo original completo.";
    }
    if (!conflict && r.id === "cea9b437d3886fb18eeca6c6dca77f7b733c410bc46463df394e2f70f2453829" &&
        r.kind === "original" && r.source_url === "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25ene2024.zip" &&
        r.bytes === 966682 && r.metadata.ingestion_kind === "city-pdf" &&
        r.metadata.archive_entry === "Medellín, José María Villa 25-1-2024.pdf" &&
        Array.isArray(r.metadata.parents) && r.metadata.parents.length === 1 &&
        r.metadata.parents[0] === "503a044d44069e1bbb39d18f5082c86cc1489ad697c823c1345920cda56b8a2b") {
      const verified = (await db.query<{ verified: boolean }>(
        "SELECT EXISTS (SELECT 1 FROM verified_city_pdf_price_resolution WHERE document_id=$1) AS verified",
        [r.id],
      )).rows[0]?.verified;
      if (verified) {
        r.metadata.price_disagreement_note = "En este PDF se corrigieron dos precios de la segunda ronda al contrastarlos con el archivo original: cilantro 6.000–6.000 y coliflor 5.000–5.000 pesos por kilogramo. Las lecturas anteriores se conservan; los precios mostrados corresponden al PDF. Esta revisión se limitó a los precios impresos.";
      }
    }
    await annotateCityPartialReview(db, r);
    annotateReviewedCityDate(r);
    annotateInputSourceAmbiguity(r);
  }
  // Display annotations for two independently audited, immutable DANE weekly
  // originals. The stored source_document period and bytes remain unchanged.
  if (r.id === "a1d2992f6bee7ce29c12ed1cee92feb31a9204ffe5546cd3276bab0cc09436e6" &&
      r.metadata.ingestion_kind === "dane-weekly-xlsx") {
    r.metadata.original_reference_period = r.reference_period;
    r.reference_period = "9 al 15 de marzo de 2024";
    r.metadata.date_resolution_note = "Período verificado: 9 al 15 de marzo de 2024. Las nueve hojas del archivo y el índice oficial de DANE indican esas fechas; solo el nombre del enlace termina en «16mar». Conservamos el archivo y su referencia original sin cambios.";
  } else if (r.id === "7bd0545a892e3a95cbaa9333510161ed14b7753949ac0fae3c24aa419729d088" &&
      r.metadata.ingestion_kind === "dane-weekly-pdf") {
    r.metadata.date_resolution_note = "Período verificado: 22 al 28 de julio de 2023. La portada y el índice oficial de DANE indican esa semana, y los precios coinciden con el anexo oficial de la misma semana. Los encabezados de las tablas de precios imprimen «15 al 21 de julio»; conservamos esa discrepancia y el PDF original.";
  } else if (r.id === "fc7e88b6cc7d6b413ed9af697c8d7388bc4c02a2e43de031be4facba0a57fd44" &&
      r.metadata.ingestion_kind === "dane-weekly-pdf") {
    r.metadata.date_resolution_note = "Período verificado: 12 al 18 de noviembre de 2022. La portada y el anexo oficial de la misma semana corroboran los precios publicados. Las tablas del PDF imprimen «22 de octubre al 18 de noviembre»; conservamos esa discrepancia y el original. Los registros cuya unidad o fecha no pudo verificarse no se presentan como precios.";
    r.metadata.date_evidence_url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/anex_12nov_al_18nov_2022.xlsx";
  }
  // This exact retained workbook has three distinct printed code conflicts.
  // Keep every literal cell and the original file; never infer a replacement.
  if (r.id === "3fb46e0841161c8521d560ed5262e730d0ae4489e233581e43d2784bb229948e" &&
      r.metadata.ingestion_kind === "rice" &&
      r.source_url === "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2026.xlsx") {
    r.metadata.source_location_code_note = "En esta hoja, 93 filas tienen códigos impresos que no concuerdan entre sí: Granada, Meta (05313 frente a 50; 27 filas); San Martín, Meta (20770 frente a 50; 44 filas); y Villanueva, Casanare (13873 frente a 85; 22 filas). Conservamos ambos códigos literales y los precios. El mercado se identifica por el municipio y departamento impresos; no sustituimos códigos de la fuente.";
  } else if (r.id === "55671429ad35195607275009f25ad6cfa91b773be0337ec4ee4af748daa90d52" &&
      r.metadata.ingestion_kind === "rice" &&
      r.source_url === "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2025.xlsx") {
    r.metadata.source_location_code_note = "En las dos hojas de este archivo, 248 filas con precio imprimen códigos municipal y departamental que no concuerdan: Granada, Meta (05313 frente a 50; 90 filas); San Martín, Meta (20770 frente a 50; 96 filas); y Villanueva, Casanare (13873 frente a 85; 62 filas). Algunas observaciones se repiten entre hojas: hay 128 combinaciones distintas de fecha, producto, lugar, códigos y precio. Conservamos ambos códigos literales y los precios; el mercado se identifica por municipio y departamento impresos sin sustituir códigos de la fuente.";
  }
  const sourceReviews = (await db.query<{ observed_on: string | null }>(
    "SELECT DISTINCT observed_on::text FROM ingestion_asset WHERE document_id=$1 AND status='review' ORDER BY 1",
    [r.id],
  )).rows;
  if (sourceReviews.length) {
    const dates = sourceReviews.map((review) => review.observed_on).filter(Boolean);
    r.metadata.review_note = `La fuente tiene referencias pendientes de verificación${dates.length ? ": " + dates.join(", ") : ""}. Conservamos el archivo original; la fecha del enlace no sustituye la fecha validada de cada precio.`;
  }
  const review = (await db.query<{ count: number; identity_note: string | null }>(
    EVIDENCE_REVIEW_COUNT_SQL,
    [r.id],
  )).rows[0];
  const reviewedRows = review?.count || 0;
  if (reviewedRows) {
    r.metadata.record_review_count = reviewedRows;
    r.metadata.record_review_note = review?.identity_note || `Hay ${reviewedRows.toLocaleString("es-CO")} ${reviewedRows === 1 ? "registro de este archivo pendiente" : "registros de este archivo pendientes"} de verificación. Se conservan en el historial y no se usan como precios publicados.`;
  }
  const correctedIdentities = (await db.query<{ count: number }>(
    "SELECT count(*)::int AS count FROM price_observation_review WHERE document_id=$1",
    [r.id],
  )).rows[0]?.count || 0;
  if (correctedIdentities) {
    r.metadata.identity_review_count = correctedIdentities;
    r.metadata.identity_review_note = `Conservamos ${correctedIdentities.toLocaleString("es-CO")} ${correctedIdentities === 1 ? "lectura anterior" : "lecturas anteriores"} con una identidad de mercado incorrecta. Esas lecturas no se usan como precios publicados; las correcciones se contrastan con este archivo original.`;
  }
  if (r.metadata.ingestion_kind === "daily") {
    let resolution = (await db.query<{ resolution: ValidatedDailyDateResolution }>(
      "SELECT details->'date_resolution' AS resolution FROM historical_price WHERE document_id=$1 AND details ? 'date_resolution' LIMIT 1",
      [r.id],
    )).rows[0]?.resolution;
    if (!resolution) {
      resolution = (await db.query<{ resolution: NonNullable<typeof resolution> }>(
        "SELECT record AS resolution FROM retained_record WHERE table_name='source_date_resolution' AND record->>'document_id'=$1 ORDER BY captured_at DESC LIMIT 1",
        [r.id],
      )).rows[0]?.resolution;
    }
    if (resolution) annotateDailyDateResolution(r, resolution);
    annotateDailySourceVariation(r);
  }
  r.parents = (
    await db.query(
      "SELECT id,title FROM source_document WHERE id=ANY($1::text[])",
      [Array.isArray(r.metadata.parents) ? r.metadata.parents : []],
    )
  ).rows;
  if (r.media_type === "text/plain")
    r.text = (
      await db.query(
        "SELECT convert_from(content,'UTF8') AS text FROM source_document WHERE id=$1",
        [r.id],
      )
    ).rows[0]?.text;
  const mid = filters.get("municipality"),
    department = filters.get("department"),
    input = filters.get("input");
  if (mid && /^\d{5}$/.test(mid)) {
    const place = (
      await db.query<{ name: string; department: string }>(
        "SELECT name,department FROM municipality WHERE id=$1",
        [mid],
      )
    ).rows[0];
    r.metadata.query_context = [
      {
        label: "Municipio de referencia",
        value: place ? `${place.name}, ${place.department} (${mid})` : mid,
      },
    ];
    const cropRows = (
      await db.query(
        "SELECT crop,variety,reference_year,physical_state,planted_ha,harvested_ha,production_t,yield_kg_ha,source_rows FROM crop_reference WHERE municipality_id=$1 AND document_id=$2",
        [mid, r.id],
      )
    ).rows;
    const suit = (
      await db.query(
        "SELECT crop_key,classification,area_ha FROM crop_suitability WHERE municipality_id=$1 AND document_id=$2",
        [mid, r.id],
      )
    ).rows;
    const soil = (
      await db.query(
        "SELECT samples,ph_samples,ph_median,ph_low,ph_high,organic_matter_median,oldest,newest FROM soil_reference WHERE municipality_id=$1 AND document_id=$2",
        [mid, r.id],
      )
    ).rows;
    r.records = [...cropRows, ...suit, ...soil];
  } else if (department && /^\d{2}$/.test(department) && !input) {
    const place = (
      await db.query<{ department: string }>(
        "SELECT department FROM municipality WHERE department_id=$1 LIMIT 1",
        [department.slice(0, 2)],
      )
    ).rows[0];
    r.metadata.query_context = [
      {
        label: "Departamento de referencia",
        value: place
          ? `${place.department} (${department.slice(0, 2)})`
          : department.slice(0, 2),
      },
    ];
    r.records = (
      await db.query(
        "SELECT crop,activity,reference_year,percentages,source_row FROM crop_calendar WHERE department_id=$1 AND document_id=$2",
        [department.slice(0, 2), r.id],
      )
    ).rows;
  } else if (input)
    r.records = (
      await db.query(
        `SELECT name,department,municipality,observed_on,presentation,price,source_locator,brand,registration FROM (SELECT *,''::text AS municipality FROM published_input_price UNION ALL SELECT * FROM published_input_municipal_price) i WHERE id=$1 AND document_id=$2 AND (cardinality($3::text[])=0 OR department=ANY($3::text[])) ORDER BY observed_on DESC LIMIT 100`,
        [input.slice(0, 500), r.id, departmentVariants(department || "")],
      )
    ).rows;
  if (
    (filters.get("food") || r.metadata?.dataset === "supply") &&
    (filters.get("market") || filters.get("product"))
  ) {
    r.records = (
      await db.query(
        `SELECT s.food_name,s.market_id,m.name market_name,s.period_start,s.first_reported_on,s.observed_on,s.quantity_kg,s.reporting_days,s.source_rows
      FROM supply_observation s JOIN market m ON m.id=s.market_id WHERE document_id=$1 AND ($2='' OR market_id=$2) AND ($3='' OR product_id=$3) AND ($4='' OR food_id=$4) AND ($5='' OR period_start::text=$5) AND s.observed_on<=CURRENT_DATE ORDER BY s.observed_on DESC LIMIT 100`,
        [
          r.id,
          (filters.get("market") || "").slice(0, 220),
          (filters.get("product") || "").slice(0, 220),
          (filters.get("food") || "").slice(0, 220),
          (filters.get("month") || "").slice(0, 10),
        ],
      )
    ).rows;
  }
  if (
    filters.get("product") &&
    !filters.get("food") &&
    r.metadata?.dataset !== "supply"
  ) {
    r.records = (
      await db.query(
        `SELECT p.name AS product_name,m.name AS market_name,o.observed_on,o.price,o.unit,o.period,o.source_locator
      FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
      WHERE o.document_id=$1 AND o.product_id=$2 AND ($3='' OR o.market_id=$3) AND ($4='' OR o.observed_on::text=$4) AND o.observed_on<=CURRENT_DATE
      ORDER BY o.observed_on DESC LIMIT 100`,
        [
          r.id,
          filters.get("product")!.slice(0, 220),
          (filters.get("market") || "").slice(0, 220),
          (filters.get("month") || "").slice(0, 10),
        ],
      )
    ).rows;
  }
  if (r.metadata?.ingestion_kind === "ocr-image") r.kind = "extract";
  if (
    String(r.metadata?.ingestion_kind || "").match(/^(international|colombia|dane)-/)
  ) {
    delete r.metadata.query_context;
    r.records = (
      await db.query(
        OFFICIAL_EVIDENCE_ROWS_SQL,
        [r.id, (filters.get("locator") || "").slice(0, 500)],
      )
    ).rows;
  }
  if (r.metadata?.ingestion_kind === "city-pdf") {
    delete r.metadata.query_context;
    r.records = (
      await db.query(
        "SELECT resolved.product_name,resolved.market_name,resolved.observed_on,resolved.presentation,resolved.quantity,resolved.source_unit,resolved.round_label,resolved.min_price,resolved.max_price,resolved.unit,resolved.min_unit_price,resolved.max_unit_price,resolved.source_page,resolved.source_locator FROM resolved_regional_price resolved JOIN published_regional_price accepted ON accepted.document_id=resolved.document_id AND accepted.source_locator=resolved.source_locator WHERE resolved.document_id=$1 ORDER BY resolved.source_page,resolved.source_locator",
        [r.id],
      )
    ).rows;
  }
  // One immutable original can be discovered by several source families. Its
  // first archive metadata must not hide subsequently verified supply tables.
  if (r.media_type === "application/pdf" || ["daily-zip-member", "daily-pdf", "supply-reference"].includes(String(r.metadata.ingestion_kind))) {
    const summary = (await db.query<{
      cells: number; reported: number; first_day: string; last_day: string; sheet: string | null; page: number | null;
    }>(
      `SELECT count(*)::int cells,
       count(*) FILTER(WHERE details->>'availability'='reported')::int reported,
       min(observed_on)::text first_day,max(observed_on)::text last_day,
       min(details->>'sheet') sheet,min((details->>'source_page')::int) page
       FROM input_reference_row WHERE document_id=$1 AND kind='supply-daily-summary'`,
      [r.id],
    )).rows[0];
    if (summary?.cells) {
      r.metadata.supply_summary_count = summary.cells;
      r.metadata.supply_summary_reported_count = summary.reported;
      r.metadata.supply_summary_sheet = summary.sheet;
      r.metadata.supply_summary_page = summary.page;
      r.metadata.supply_summary_note = `Abastecimiento diario${summary.page !== null ? " (las columnas marcadas p son provisionales)" : " provisional"}: ${summary.reported.toLocaleString("es-CO")} valores en toneladas, del ${summary.first_day} al ${summary.last_day}. Los blancos indican datos no reportados. Los totales por mercado y el total de los mercados informados se conservan por separado; no se suman a los registros por alimento ni son precios.`;
      if (showsSupplySummaryRecords(filters)) r.records = (await db.query(
        `SELECT kind,observed_on,name,category,source_locator,
         details->>'unit' unit,details->'quantity_tonnes' quantity_tonnes,
         details->>'aggregation_level' aggregation_level,details
         FROM input_reference_row WHERE document_id=$1 AND kind='supply-daily-summary'
         AND ($2='' OR source_locator=$2)
         ORDER BY observed_on DESC,source_locator LIMIT 500`,
        [r.id, (filters.get("locator") || "").slice(0, 500)],
      )).rows;
    }
  }
  if (r.media_type === "application/pdf" || ["supply-reference", "supply-reference-pdf"].includes(String(r.metadata.ingestion_kind))) {
    const canonicalVersion = (await db.query<{ version: number }>(
      SUPPLY_PERIOD_CANONICAL_VERSION_SQL, [r.id],
    )).rows[0]?.version;
    const summary = (await db.query<{
      tonnes: number; percentages: number; cells: number; first_day: string; last_day: string;
      sheet: string | null; page: number | null; frequency: string;
    }>(
      SUPPLY_PERIOD_SUMMARY_SQL, [r.id, canonicalVersion ?? null],
    )).rows[0];
    if (summary?.cells) {
      r.metadata.supply_summary_count = summary.cells;
      r.metadata.supply_summary_sheet = summary.sheet;
      r.metadata.supply_summary_page = summary.page;
      if (r.metadata.review_note) r.metadata.review_note = "Hay tablas de abastecimiento pendientes de verificación; sus celdas no se publican como referencias. Se conserva el archivo original completo.";
      const period = summary.frequency === "first_fortnight" ? "primera quincena de cada mes" : "mes completo";
      r.metadata.supply_summary_note = `Abastecimiento por período (${period}): ${summary.tonnes.toLocaleString("es-CO")} celdas de toneladas y ${summary.percentages.toLocaleString("es-CO")} de porcentajes, del ${summary.first_day} al ${summary.last_day}. Se conserva la precisión de cada original; los PDF pueden estar redondeados. Los blancos indican datos no reportados. Son resúmenes no aditivos: no se suman entre mercados, grupos y totales, ni se incorporan a los registros por alimento o a los precios. Cobertura tipificada: tablas de totales de mercados${r.metadata.ingestion_kind === "supply-reference" ? ", grupos y participaciones con fechas verificadas" : "; otras tablas y gráficos permanecen en el original"}.`;
      if (showsSupplySummaryRecords(filters)) r.records = (await db.query(
        SUPPLY_PERIOD_ROWS_SQL,
        [r.id, (filters.get("locator") || "").slice(0, 500), canonicalVersion ?? null],
      )).rows;
    }
  }
  return r;
}
