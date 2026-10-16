import "server-only";
import { database, WINDOW } from "./db";
import { reconcileInputCatalog } from "./input-identities";
import { PRICE_QUOTE_VALUES, CITY_LOOSE_LATEST_QUOTES, CITY_RECENT_LOOSE_LATEST_QUOTES, CITY_LOOSE_UNIT_AMBIGUITY, cityPriceQuotes, withQuoteClassifications } from "./price-quotes";
import { compareQuotes, summarizeComparisons } from "../comparison-math";
import { comparisonDisplay } from "../comparison-display";
import { departmentLabel, departmentVariants } from "../filter-labels";
import { resolveMarketAlias } from "./market-alias";
import { CORABASTOS_CITY_MARKET_ID, cityMarketIdSql, cityMarketJoinSql, cityMarketSeekSql, cityMarketNameSql, cityMarketNamesForIdSql, resolveCityMarketId } from "./city-market-alias";
import { cityAliasConflicts } from "./market-sql";
import { corabastosAllHistoryQuotes } from "./comparison-corabastos-all-history";
import { canonicalInputLocation, inputLocationId, latestInputLocations } from "../input-locations";
import { assertInputIdentityMembers, assertNoLatestInputIdentityConflicts, latestEquivalentInputRows, resolveInputIdentity } from "../input-identity-equivalence";
import type {
  ComparisonData,
  ComparisonKind,
  ComparisonLocation,
  ComparisonQuote,
} from "../comparison-types";

const NATIONAL = "__national__";
type Requested = Record<string, string>;
type Options = { locations: ComparisonLocation[]; series: string[];
  nativeMunicipalities?: Record<string, string[]> };
const optionsCache = new Map<
  string,
  { expires: number; value: Promise<Options> }
>();
const comparisonCache = new Map<
  string,
  { expires: number; result: Promise<ComparisonData> }
>();

async function options(
  kind: ComparisonKind,
  scope: string,
  history: string,
): Promise<Options> {
  const key = [kind, scope, history].join(":");
  const cached = optionsCache.get(key);
  if (cached && cached.expires > Date.now()) return cached.value;
  const value = (async () => {
    const period = history === "all" ? "observed_on <= CURRENT_DATE" : WINDOW;
    if (kind === "markets") {
      const rows = (
        await database().query(
          // Seek one published observation per market and series. A full-history
          // DISTINCT over every observation can exceed the request deadline.
          `SELECT m.id,m.name,s.series FROM market m CROSS JOIN (
            VALUES ('farmgate'::text,'dane-milk-farm'::text),
              ('mill','dane-rice-mill'),('coffee','fnc')
          ) s(series,source_id)
          WHERE EXISTS (SELECT 1 FROM published_price_observation o
            JOIN product p ON p.id=o.product_id
            WHERE o.market_id=m.id AND o.source_id=s.source_id AND ${period}
            OFFSET 0)
          UNION
          SELECT m.id,m.name,'monthly'::text AS series FROM market m
          WHERE EXISTS (SELECT 1 FROM published_price_observation o
            JOIN product p ON p.id=o.product_id
            WHERE o.market_id=m.id AND o.source_id NOT IN ('dane-milk-farm','dane-rice-mill','fnc')
              AND ${period} OFFSET 0)
          UNION
          SELECT ${cityMarketIdSql()} AS id,${cityMarketNameSql()} AS name,'city'::text AS series FROM market m
          WHERE EXISTS (SELECT 1 FROM published_regional_price r
            WHERE ${cityMarketSeekSql()} AND ${period.replace(/\bobserved_on\b/g, "r.observed_on")} OFFSET 0)
          ORDER BY name`,
        )
      ).rows;
      return {
        locations: [
          ...new Map(
            rows.map((r) => [
              r.id,
              {
                id: r.id,
                name: r.name,
                series: rows.filter((q) => q.id === r.id).map((q) => q.series),
              },
            ]),
          ).values(),
        ],
        series: [...new Set<string>(rows.map((r) => r.series))].sort((a, b) =>
          a === "city" ? -1 : b === "city" ? 1 : a.localeCompare(b),
        ),
      };
    }
    const municipal = scope === "municipality";
    const latestAllowedDate = history === "all"
      ? "CURRENT_DATE"
      : "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date";
    // Location names carry no price claims. Avoid running publication checks on
    // millions of historical observations just to build these picker labels.
    const rows = (
      await database().query(
        municipal ? `WITH RECURSIVE locations AS (
          (SELECT department,municipality,observed_on FROM input_municipal_price
            WHERE observed_on<=${latestAllowedDate}
            ORDER BY department,municipality,observed_on DESC LIMIT 1)
          UNION ALL
          SELECT next.* FROM locations previous CROSS JOIN LATERAL (
            SELECT department,municipality,observed_on FROM input_municipal_price
            WHERE (department,municipality)>(previous.department,previous.municipality)
              AND observed_on<=${latestAllowedDate}
            ORDER BY department,municipality,observed_on DESC LIMIT 1
          ) next
        ) SELECT department,municipality FROM locations WHERE ${period}
          ORDER BY department,municipality`
        : `SELECT DISTINCT department FROM input_price WHERE ${period} ORDER BY department`,
      )
    ).rows;
    const nativeMunicipalities: Record<string, string[]> = {};
    if (municipal) for (const row of rows) {
      const id = inputLocationId(row.department, row.municipality, true);
      (nativeMunicipalities[id] ||= []).push(row.municipality);
    }
    return {
      locations: [...new Map(rows.map((r) => {
        const id = inputLocationId(r.department, r.municipality, municipal);
        return [id, { id, name: municipal
          ? `${JSON.parse(id)[1]}, ${departmentLabel(r.department)}` : departmentLabel(r.department) }];
      })).values()],
      series: [municipal ? "input-municipal" : "input-department"],
      ...(municipal ? { nativeMunicipalities } : {}),
    };
  })();
  optionsCache.set(key, { expires: Date.now() + 300_000, value });
  try {
    return await value;
  } catch (error) {
    optionsCache.delete(key);
    throw error;
  }
}

async function marketQuotes(
  location: string,
  series: string,
  history: string,
  product: string,
  identities?: string[],
): Promise<ComparisonQuote[]> {
  if (series === "city" && location === CORABASTOS_CITY_MARKET_ID
    && history === "all" && !product && !identities?.length) {
    return corabastosAllHistoryQuotes();
  }
  if (series === "city" && location === NATIONAL && identities?.length) {
    const result = await database().query(
      history === "all" ? CITY_LOOSE_LATEST_QUOTES : CITY_RECENT_LOOSE_LATEST_QUOTES,
      [identities],
    );
    if (!result.rows.length) return [];
    const ambiguous = new Set<string>((await database().query(CITY_LOOSE_UNIT_AMBIGUITY, [
      result.rows.map((row) => row.id),
      result.rows.map((row) => row.document_id),
      result.rows.map((row) => row.source_locator),
    ])).rows.map((row) => row.product_id));
    if (!ambiguous.size) return withQuoteClassifications(result.rows);
    const period = history === "all" ? "r.observed_on <= CURRENT_DATE" : WINDOW.replaceAll("observed_on", "r.observed_on");
    const generic = await database().query(
      `WITH quotes AS (${cityPriceQuotes(false, `WHERE r.product_id=ANY($1::text[]) AND ${period}`)})
       SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
         product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
         market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
         price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
       FROM quotes WHERE ${period.replaceAll("r.observed_on", "observed_on")}
       ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,
      [[...ambiguous]],
    );
    return withQuoteClassifications([
      ...result.rows.filter((row) => !ambiguous.has(row.id)), ...generic.rows,
    ]);
  }
  const period = history === "all" ? "observed_on <= CURRENT_DATE" : WINDOW;
  // The city revision sort must see only the selected identities. Sorting the
  // whole historical city archive before applying these filters times out.
  const city = series === "city";
  const cityArgs: (string | string[])[] = [];
  const cityFilters: string[] = [];
  if (city && location !== NATIONAL) {
    cityArgs.push(location);
    cityFilters.push(`${cityMarketNamesForIdSql(`$${cityArgs.length}`)} AND ${cityMarketIdSql()}=$${cityArgs.length}`);
  }
  if (city && product) {
    cityArgs.push(product);
    cityFilters.push(`r.product_id=$${cityArgs.length}`);
  }
  if (city && identities?.length) {
    cityArgs.push(identities);
    cityFilters.push(`r.product_id=ANY($${cityArgs.length}::text[])`);
  }
  if (city) cityFilters.push(period);
  // The recent Corabastos overview repeats the same conflict check for every
  // product. Compute its published alias witnesses once for that date window.
  const precomputedAliasConflicts = city && history === "recent"
    && location === CORABASTOS_CITY_MARKET_ID
    && !product && !identities?.length;
  const quotes = city
    ? cityPriceQuotes(false, `WHERE ${cityFilters.join(" AND ")}`,
        false, false, precomputedAliasConflicts)
    : PRICE_QUOTE_VALUES;
  const result = await database().query(
    `WITH ${precomputedAliasConflicts ? `${cityAliasConflicts(period)}, ` : ""}quotes AS (${quotes})
    SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
      product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
      market_id AS location_id,source_market_id,market_name AS location_name,region AS department,
      price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page,source_units
    FROM quotes WHERE ${city ? "true AND" : "($1='' OR market_id=$1) AND series=$2 AND ($3='' OR product_id=$3) AND ($4::text[] IS NULL OR product_id=ANY($4)) AND"} ${period}
    ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,
    city
      ? cityArgs
      : [location === NATIONAL ? "" : location, series, product, identities || null],
  );
  // Classification cannot affect quote winners or arithmetic. Enrich only the
  // selected current rows, preserving the exact original/locator correction.
  return withQuoteClassifications(result.rows);
}

async function inputQuotes(
  location: string,
  scope: string,
  history: string,
  product: string,
  identities?: string[],
  nativeMunicipalities: string[] = [],
): Promise<ComparisonQuote[]> {
  const municipal = scope === "municipality";
  let department = "",
    municipality = "";
  if (location !== NATIONAL) {
    if (municipal) [department, municipality] = JSON.parse(location);
    else department = location;
  }
  const period = history === "all" ? "observed_on <= CURRENT_DATE" : WINDOW;
  const table = municipal ? "input_municipal_price" : "input_price";
  const projection = municipal ? "input_municipal_latest_raw" : "input_department_latest_raw";
  const keys = `p.id,p.department${municipal ? ",p.municipality" : ""}`;
  const published = `published_${table}`;
  const municipalityNames = municipal && municipality
    ? [...new Set([...nativeMunicipalities, municipality])]
    : [];
  const selectedIds = product ? resolveInputIdentity(product).memberIds : [];
  const identityIds = identities?.length
    ? [...new Set(identities.flatMap((identity) => resolveInputIdentity(identity).memberIds))]
    : null;
  const args = [departmentVariants(department), municipalityNames, selectedIds, identityIds];
  const filter = `(cardinality($1::text[])=0 OR p.department=ANY($1::text[])) AND (cardinality($2::text[])=0 OR ${municipal ? "p.municipality" : "''"}=ANY($2::text[]))
    AND (cardinality($3::text[])=0 OR p.id=ANY($3)) AND ($4::text[] IS NULL OR p.id=ANY($4))
    AND ${period.replaceAll("observed_on", "p.observed_on")}`;
  // A broad published-view read evaluates alias/revision checks over millions
  // of raw rows. Seek the latest physical row for each exact identity/location
  // first; only withdrawn PDFs and legacy aliases need that view's correction.
  const rawQuery = `SELECT DISTINCT ON(${keys}) p.* FROM ${table} p WHERE ${filter}
    ORDER BY ${keys},p.observed_on DESC,p.price`;
  const projectedQuery = `WITH state AS MATERIALIZED (
      SELECT coalesce((SELECT projection_epoch=source_epoch AND
        asof_bogota=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
        FROM input_latest_projection_state WHERE scope=$5),false) AS ready
    ) SELECT s.ready,p.* FROM state s LEFT JOIN LATERAL (
      SELECT p.* FROM ${projection} l JOIN ${table} p ON p.id=l.id
        AND p.department=l.department ${municipal ? "AND p.municipality=l.municipality" : ""}
        AND p.observed_on=l.observed_on WHERE s.ready AND ${filter}
    ) p ON s.ready`;
  let projectionUnavailable = false;
  const readRaw = async (ids: string[] | null): Promise<any[]> => {
    try {
      if (!projectionUnavailable) {
        try {
          const projected = (await database().query(projectedQuery,
            [args[0], args[1], args[2], ids, municipal ? "municipality" : "department"])).rows;
          if (projected[0]?.ready === true)
            return projected.filter((row) => row.id !== null)
              .map(({ ready: _ready, ...row }) => row);
          projectionUnavailable = true;
        } catch (error) {
          if (!["42P01", "55000"].includes((error as { code?: string }).code || "")) throw error;
          projectionUnavailable = true;
        }
      }
      if (ids && ids.length > 10) {
        const middle = Math.ceil(ids.length / 2);
        return [...await readRaw(ids.slice(0, middle)), ...await readRaw(ids.slice(middle))];
      }
      return (await database().query(rawQuery,
        [args[0], args[1], args[2], ids])).rows;
    } catch (error) {
      if ((error as { code?: string }).code !== "57014" || !ids || ids.length <= 1)
        throw error;
      const middle = Math.ceil(ids.length / 2);
      return [...await readRaw(ids.slice(0, middle)), ...await readRaw(ids.slice(middle))];
    }
  };
  const raw: Record<string, any>[] = [];
  if (identityIds?.length && history === "all") {
    for (let offset = 0; offset < identityIds.length;) {
      const batchSize = projectionUnavailable ? 10 : 80;
      raw.push(...await readRaw(identityIds.slice(offset, offset + batchSize)));
      offset += batchSize;
    }
  } else raw.push(...await readRaw(identityIds));
  if (!raw.length) return [];
  const documentIds = [...new Set(raw.map((row) => row.document_id))];
  const ids = [...new Set(raw.map((row) => row.id))];
  const [withdrawn, aliases] = await Promise.all([
    database().query(
      `SELECT document_id,max(substring(processor_version from '([0-9]+)$')::numeric) AS version
       FROM ingestion_checkpoint WHERE document_id=ANY($1::text[]) AND step='inputs-pdf:published'
       AND processor_version ~ '^inputs-pdf-v[0-9]+$' GROUP BY document_id`, [documentIds],
    ),
    database().query(
      "SELECT DISTINCT legacy_id FROM input_identity_alias WHERE legacy_id=ANY($1::text[])", [ids],
    ),
  ]);
  const versions = new Map(withdrawn.rows.map((row) => [row.document_id, Number(row.version)]));
  const aliased = new Set(aliases.rows.map((row) => row.legacy_id));
  const needsPublished = (row: typeof raw[number]) => {
    const parserVersion = Number(/; inputs-pdf-v([0-9]+)$/.exec(row.source_locator || "")?.[1] || 0);
    return aliased.has(row.id) || (versions.get(row.document_id) || 0) > parserVersion;
  };
  const flagged = raw.filter(needsPublished);
  const verified = [];
  for (let offset = 0; offset < flagged.length; offset += 40) {
    verified.push(...(await database().query(
      `SELECT p.* FROM jsonb_to_recordset($1::jsonb)
        AS f(id text,department text,municipality text) CROSS JOIN LATERAL (
          SELECT p.* FROM ${published} p WHERE p.id=f.id AND p.department=f.department
            ${municipal ? "AND p.municipality=f.municipality" : ""}
            AND ${period.replaceAll("observed_on", "p.observed_on")}
          ORDER BY p.observed_on DESC,p.price LIMIT 1
        ) p`,
      [JSON.stringify(flagged.slice(offset, offset + 40).map((row) => ({ id: row.id,
        department: row.department, municipality: municipal ? row.municipality : "" })))],
    )).rows);
  }
  const key = (row: typeof raw[number]) => JSON.stringify([row.id,row.department,municipal ? row.municipality : ""]);
  const replacements = new Map(verified.map((row) => [key(row), row]));
  const winners = raw.flatMap((row) => needsPublished(row)
    ? (replacements.has(key(row)) ? [replacements.get(key(row))] : []) : [row]);
  const selectedIdentityIds = [...selectedIds, ...(identityIds || [])];
  assertInputIdentityMembers(winners, selectedIdentityIds);
  const hasIdentityEquivalence = selectedIdentityIds.some((identity) =>
    resolveInputIdentity(identity).equivalent,
  ) || winners.some((row) => resolveInputIdentity(row.id, row).equivalent);
  // Reconcile exact-ID source revisions before assigning canonical IDs. That
  // keeps the historical revision rule from treating two retained members as
  // duplicate rows simply because their display names become equal.
  const reconciledWinners = !product && hasIdentityEquivalence
    ? await reconcileInputCatalog(winners) : winners;
  assertNoLatestInputIdentityConflicts(reconciledWinners);
  const latestWinners = hasIdentityEquivalence
    ? latestEquivalentInputRows(reconciledWinners)
    : latestInputLocations(reconciledWinners);
  const quotes = latestWinners.map((p) => ({
    id: p.id,name: p.name,category: p.category,category_path: p.category.split(" > "),
    presentation: p.presentation,units: p.presentation,unit: "presentation",
    series: municipal ? "input-municipal" : "input-department",
    location_id: inputLocationId(p.department,p.municipality,municipal),
    location_name: municipal ? `${p.municipality}, ${p.department}` : p.department,
    department: p.department,municipality: municipal ? p.municipality : "",
    brand: p.brand,registration: p.registration,product_line: p.product_line,
    price: p.price,date: p.observed_on,observed_on: p.observed_on,
    document_id: p.document_id,source_locator: p.source_locator,
    ...(p.source_input_id ? { source_input_id: p.source_input_id, source_name: p.source_name } : {}),
  }));
  const resolved = product || hasIdentityEquivalence ? quotes : await reconcileInputCatalog(quotes);
  return resolved.map(({ observed_on: _observedOn, ...quote }) => quote);
}

async function inputReferenceBatch(
  location: string,
  scope: string,
  history: string,
  product: string,
  identities: string[],
  nativeMunicipalities: string[] = [],
): Promise<ComparisonQuote[]> {
  if (history === "all") return inputQuotes(location, scope, history, product, identities, nativeMunicipalities);
  const batchSize = 40;
  if (identities.length > batchSize) {
    const rows: ComparisonQuote[] = [];
    for (let offset = 0; offset < identities.length; offset += batchSize)
      rows.push(...await inputReferenceBatch(location, scope, history, product,
        identities.slice(offset, offset + batchSize), nativeMunicipalities));
    return rows;
  }
  try {
    return await inputQuotes(location, scope, history, product, identities, nativeMunicipalities);
  } catch (error) {
    // Database contention can make an otherwise small cold read exceed the
    // statement deadline. Retry that read in smaller pieces without dropping
    // identities or changing the freshness/normalization rules.
    if ((error as { code?: string }).code !== "57014" || identities.length <= 1)
      throw error;
    const middle = Math.ceil(identities.length / 2);
    return [
      ...(await inputReferenceBatch(
        location,
        scope,
        history,
        product,
        identities.slice(0, middle),
        nativeMunicipalities,
      )),
      ...(await inputReferenceBatch(
        location,
        scope,
        history,
        product,
        identities.slice(middle),
        nativeMunicipalities,
      )),
    ];
  }
}

async function marketReferenceBatch(
  location: string,
  series: string,
  history: string,
  product: string,
  identities: string[],
): Promise<ComparisonQuote[]> {
  try {
    return await marketQuotes(location, series, history, product, identities);
  } catch (error) {
    if ((error as { code?: string }).code !== "57014" || identities.length <= 1)
      throw error;
    const middle = Math.ceil(identities.length / 2);
    return [
      ...(await marketReferenceBatch(location, series, history, product, identities.slice(0, middle))),
      ...(await marketReferenceBatch(location, series, history, product, identities.slice(middle))),
    ];
  }
}

async function computeComparison(
  kind: ComparisonKind,
  requested: Requested,
): Promise<ComparisonData> {
  const scope =
    requested.scope === "municipality" ? "municipality" : "department";
  const history = requested.history === "all" ? "all" : "recent";
  const available = await options(kind, scope, history);
  const requestedA =
    requested.a ||
    (kind === "inputs" && requested.department
      ? scope === "municipality"
        ? JSON.stringify([requested.department, requested.municipality || ""])
        : requested.department
      : "");
  const proposedA = kind === "inputs" ? canonicalInputLocation(requestedA, scope === "municipality") : requestedA;
  const proposedB = kind === "inputs" ? canonicalInputLocation(requested.b || "", scope === "municipality") : requested.b;
  const preferredLocations = available.locations.filter(
    (l) =>
      !requested.series || !l.series || l.series.includes(requested.series),
  );
  const defaults = preferredLocations.length
    ? preferredLocations
    : available.locations;
  const defaultLocation =
    defaults.find((l) => l.series?.includes("city")) ||
    defaults.find((l) => l.series?.includes("monthly")) ||
    defaults[0];
  const a = defaults.some((l) => l.id === proposedA)
    ? proposedA
    : defaultLocation?.id || "";
  const b =
    proposedB &&
    proposedB !== a &&
    available.locations.some((l) => l.id === proposedB)
      ? proposedB
      : NATIONAL;
  const localSeries =
    available.locations.find((l) => l.id === a)?.series || available.series;
  const series = available.series.includes(requested.series)
    ? requested.series
    : available.series.find((s) => localSeries.includes(s)) || "city";
  const dates = requested.dates === "same" ? "same" : "latest";
  const product = requested.product || "";
  const read = (location: string) =>
    kind === "markets"
      ? marketQuotes(location, series, history, product)
      : inputQuotes(location, scope, history, product, undefined,
          available.nativeMunicipalities?.[location] || []);
  let base: ComparisonQuote[] = [],
    other: ComparisonQuote[] = [];
  if (a && kind === "inputs") {
    base = await read(a);
    if (requested.view !== "prices" && base.length) {
      const identities = [...new Set(base.map((q) => q.id))];
      // One filtered published-view read covers the exact base identities.
      // If live database load exceeds the statement deadline, the existing
      // bounded retry splits only this read without dropping identities.
      other = await inputReferenceBatch(b, scope, history, product, identities,
        available.nativeMunicipalities?.[b] || []);
      if (!product) other = (await reconcileInputCatalog(other.map((quote) => ({
        ...quote, observed_on: quote.date,
        department: quote.department || "",
      })))).map(({ observed_on: _observedOn, ...quote }) => quote);
    }
  } else if (a) {
    base = await read(a);
    if (requested.view !== "prices" && base.length) {
      // A's product identities define every possible match. Reading all other
      // products nationwide adds history scans without adding a comparison.
      // Retain all markets/packages/dates for these IDs so unmatched rows and
      // the national-average population remain unchanged.
      const identities = [...new Set(base.map((quote) => quote.id))];
      // A city can contribute over one hundred retained products. With
      // 12-identity batches, the recent national read repeats the regional
      // revision join ten times for a normal city. The same bounded 50-key
      // batch used by all-history keeps exact quote selection and can still
      // split on a 57014 statement timeout below.
      const batchSize = series === "city" ? 50 : 12;
      for (let offset = 0; offset < identities.length; offset += batchSize) {
        other.push(...await marketReferenceBatch(b, series, history, product, identities.slice(offset, offset + batchSize)));
      }
    }
  }
  const rows = compareQuotes(
    base,
    other,
    dates === "same",
    requested.sources === "true" && Boolean(product),
    b === NATIONAL,
  );
  const { nativeMunicipalities: _privateMunicipalities, ...publicAvailable } = available;
  return comparisonDisplay({
    kind,
    filters: { a, b, series, scope, history, dates, product },
    ...publicAvailable,
    a_name:
      available.locations.find((l) => l.id === a)?.name || "Sin ubicación",
    b_name:
      b === NATIONAL
        ? "Promedio de Colombia"
        : available.locations.find((l) => l.id === b)?.name || "",
    rows,
    ...summarizeComparisons(rows),
  });
}

/** Shares concurrent requests and keeps a bounded cache of final summaries.
 * Cached reads have the same five-minute freshness contract as the HTTP API.
 */
export async function comparison(
  kind: ComparisonKind,
  requested: Requested,
): Promise<ComparisonData> {
  if (kind === "markets") {
    const db = database();
    const citySelection = requested.series === "city" || !requested.series;
    const a = requested.a ? await resolveMarketAlias(db, requested.a) : requested.a;
    const b = requested.b ? await resolveMarketAlias(db, requested.b) : requested.b;
    requested = { ...requested,
      a: citySelection && a ? resolveCityMarketId(a) : a,
      b: citySelection && b ? resolveCityMarketId(b) : b,
    };
  }
  // Omitted defaults and explicit UI defaults represent the same query.
  // Reuse their in-flight work instead of running duplicate national scans.
  requested = {
    ...requested,
    scope: requested.scope === "municipality" ? "municipality" : "department",
    history: requested.history === "all" ? "all" : "recent",
    dates: requested.dates === "same" ? "same" : "latest",
    b: requested.b || NATIONAL,
  };
  const fields = [
    "a",
    "b",
    "department",
    "municipality",
    "series",
    "scope",
    "history",
    "dates",
    "product",
    "view",
    "sources",
  ];
  const key = JSON.stringify([
    kind,
    ...fields.map((field) => requested[field] || ""),
  ]);
  const found = comparisonCache.get(key);
  if (found && found.expires > Date.now()) return found.result;
  const result = computeComparison(kind, requested);
  comparisonCache.set(key, { expires: Date.now() + 300_000, result });
  while (comparisonCache.size > 8)
    comparisonCache.delete(comparisonCache.keys().next().value!);
  try {
    return await result;
  } catch (error) {
    if (comparisonCache.get(key)?.result === result)
      comparisonCache.delete(key);
    throw error;
  }
}
