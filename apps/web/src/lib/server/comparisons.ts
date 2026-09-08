import "server-only";
import { database, WINDOW } from "./db";
import { PRICE_QUOTES } from "./price-quotes";
import { compareQuotes, summarizeComparisons } from "../comparison-math";
import type {
  ComparisonData,
  ComparisonKind,
  ComparisonLocation,
  ComparisonQuote,
} from "../comparison-types";

const NATIONAL = "__national__";
type Requested = Record<string, string>;
type Options = { locations: ComparisonLocation[]; series: string[] };
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
          `WITH quotes AS (${PRICE_QUOTES}) SELECT DISTINCT market_id AS id,market_name AS name,series FROM quotes WHERE ${period} ORDER BY name`,
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
    // Location names carry no price claims. Avoid running publication checks on
    // millions of historical observations just to build these picker labels.
    const rows = (
      await database().query(
        `SELECT DISTINCT department${municipal ? ",municipality" : ""} FROM ${municipal ? "input_municipal_price" : "input_price"} WHERE ${period} ORDER BY department${municipal ? ",municipality" : ""}`,
      )
    ).rows;
    return {
      locations: rows.map((r) => ({
        id: municipal
          ? JSON.stringify([r.department, r.municipality])
          : r.department,
        name: municipal ? `${r.municipality}, ${r.department}` : r.department,
      })),
      series: [municipal ? "input-municipal" : "input-department"],
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
): Promise<ComparisonQuote[]> {
  const period = history === "all" ? "observed_on <= CURRENT_DATE" : WINDOW;
  const result = await database().query(
    `WITH quotes AS (${PRICE_QUOTES})
    SELECT DISTINCT ON(product_id,market_id,presentation,units,unit,series)
      product_id AS id,product_name AS name,category,category_path,presentation,units,unit,series,
      market_id AS location_id,market_name AS location_name,region AS department,
      price,min_price,max_price,observed_on AS date,document_id,source_locator,source_page
    FROM quotes WHERE ($1='' OR market_id=$1) AND series=$2 AND ($3='' OR product_id=$3) AND ${period}
    ORDER BY product_id,market_id,presentation,units,unit,series,observed_on DESC,document_id`,
    [location === NATIONAL ? "" : location, series, product],
  );
  return result.rows;
}

async function inputQuotes(
  location: string,
  scope: string,
  history: string,
  product: string,
  identities?: string[],
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
  // Build identities through narrow covering indexes, then read one published
  // row per identity. This also finds the previous valid observation when a
  // publisher revision has withdrawn the newest raw row. The document index
  // on ingestion_asset keeps each publication check bounded.
  const result = await database().query(
    `WITH identities AS MATERIALIZED (
      SELECT id,department${municipal ? ",municipality" : ""},max(observed_on) AS latest_date
      FROM ${table} WHERE ($1='' OR department=$1) AND ($2='' OR ${municipal ? "municipality" : "''"}=$2)
        AND ($3='' OR id=$3) AND ($4::text[] IS NULL OR id=ANY($4)) AND ${period}
      GROUP BY id,department${municipal ? ",municipality" : ""}
    )
    SELECT p.id,p.name,p.category,string_to_array(p.category,' > ') AS category_path,p.presentation,p.presentation AS units,
      'presentation'::text AS unit,'${municipal ? "input-municipal" : "input-department"}'::text AS series,
      ${municipal ? "json_build_array(p.department,p.municipality)::text" : "p.department"} AS location_id,
      ${municipal ? "p.municipality || ', ' || p.department" : "p.department"} AS location_name,
      p.department,${municipal ? "p.municipality" : "''::text AS municipality"},p.brand,p.registration,p.product_line,
      p.price,p.observed_on AS date,p.document_id,p.source_locator
    FROM identities i CROSS JOIN LATERAL (
      SELECT p.* FROM published_${table} p WHERE p.id=i.id AND p.department=i.department
      ${municipal ? "AND p.municipality=i.municipality" : ""} AND p.observed_on<=i.latest_date AND ${period}
      ORDER BY p.observed_on DESC LIMIT 1
    ) p`,
    [department, municipality, product, identities || null],
  );
  return result.rows;
}

async function inputReferenceBatch(
  location: string,
  scope: string,
  history: string,
  product: string,
  identities: string[],
): Promise<ComparisonQuote[]> {
  try {
    return await inputQuotes(location, scope, history, product, identities);
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
      )),
      ...(await inputReferenceBatch(
        location,
        scope,
        history,
        product,
        identities.slice(middle),
      )),
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
  const proposedA =
    requested.a ||
    (kind === "inputs" && requested.department
      ? scope === "municipality"
        ? JSON.stringify([requested.department, requested.municipality || ""])
        : requested.department
      : "");
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
    requested.b &&
    requested.b !== a &&
    available.locations.some((l) => l.id === requested.b)
      ? requested.b
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
      : inputQuotes(location, scope, history, product);
  let base: ComparisonQuote[] = [],
    other: ComparisonQuote[] = [];
  if (a && kind === "inputs") {
    base = await read(a);
    if (requested.view !== "prices" && base.length) {
      const identities = [...new Set(base.map((q) => q.id))];
      // Keep each read below the database statement deadline even when a
      // full-history comparison needs thousands of cold index lookups.
      for (let offset = 0; offset < identities.length; offset += 80) {
        other.push(
          ...(await inputReferenceBatch(
            b,
            scope,
            history,
            product,
            identities.slice(offset, offset + 80),
          )),
        );
      }
    }
  } else if (a) {
    [base, other] = await Promise.all([
      read(a),
      requested.view === "prices" ? Promise.resolve([]) : read(b),
    ]);
  }
  const rows = compareQuotes(
    base,
    other,
    dates === "same",
    requested.sources === "true" && Boolean(product),
    b === NATIONAL,
  );
  return {
    kind,
    filters: { a, b, series, scope, history, dates, product },
    ...available,
    a_name:
      available.locations.find((l) => l.id === a)?.name || "Sin ubicación",
    b_name:
      b === NATIONAL
        ? "Promedio de Colombia"
        : available.locations.find((l) => l.id === b)?.name || "",
    rows,
    ...summarizeComparisons(rows),
  };
}

/** Shares concurrent requests and keeps a bounded cache of final summaries.
 * Cached reads have the same five-minute freshness contract as the HTTP API.
 */
export async function comparison(
  kind: ComparisonKind,
  requested: Requested,
): Promise<ComparisonData> {
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
