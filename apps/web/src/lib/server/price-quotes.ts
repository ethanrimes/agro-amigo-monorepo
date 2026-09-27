import "server-only";
import { currentClassifications } from "../price-classification";
import { database, WINDOW } from "./db";
import { summaryReferencesForProduct } from "./summary-references";

/** Shared quote identities for product filters, maps and market comparisons.
 * City prices are per original package; monthly references keep their base unit.
 * Latest round / publisher revision wins within the same dated quote identity.
 */
function cityPriceQuotes(classify: boolean) { return `
  SELECT product_id,market_id,market_name,city,region,product_name,category,category_path,
    observed_on,(min_price+max_price)/2 AS price,min_price,max_price,unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,document_id,source_locator,source_url,'daily'::text AS period,source_page FROM (
    SELECT DISTINCT ON(r.product_id,m.id,r.observed_on,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)))
      r.*,m.id AS market_id,m.city,m.region,
      ${classify ? "coalesce(c.category_path,string_to_array(r.category,' > '))" : "string_to_array(r.category,' > ')"} AS category_path,
      r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) AS units,d.source_url
    FROM regional_price r JOIN market m ON m.name=r.market_name
    JOIN source_document d ON d.id=r.document_id
    ${classify ? "LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator" : ""}
    ORDER BY r.product_id,m.id,r.observed_on,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)),r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city`; }
export const CITY_PRICE_QUOTES = cityPriceQuotes(true);

function priceQuotes(city: string) { return `
  SELECT o.product_id,m.id AS market_id,m.name AS market_name,m.city,m.region,
    p.name AS product_name,p.category,ARRAY[p.category]::text[] AS category_path,
    o.observed_on,o.price,o.min_price,o.max_price,o.unit,
    'Por unidad de medida'::text AS presentation,
    CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
    CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
    o.document_id,o.source_locator,o.source_url,o.period,1::integer AS source_page
  FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
  UNION ALL
${city}`; }
export const PRICE_QUOTES = priceQuotes(CITY_PRICE_QUOTES);
// Dates, prices and revision winners do not depend on classification metadata.
// Fetch that metadata only for the selected display rows, not each historical
// observation feeding an aggregate or a picker.
export const PRICE_QUOTE_VALUES = priceQuotes(cityPriceQuotes(false));

export async function withQuoteClassifications<T extends {
  series: string; document_id: string; source_locator: string; category_path: string[];
}>(rows: T[]): Promise<T[]> {
  const city = rows.filter((row) => row.series === "city");
  if (!city.length) return rows;
  const paths = (await database().query(`
    SELECT selected.document_id,selected.source_locator,c.category_path
    FROM unnest($1::text[],$2::text[]) AS selected(document_id,source_locator)
    CROSS JOIN LATERAL (
      SELECT category_path FROM regional_classification c
      WHERE c.document_id=selected.document_id AND c.source_locator=selected.source_locator OFFSET 0
    ) c`, [city.map((row) => row.document_id), city.map((row) => row.source_locator)])).rows;
  const bySource = new Map(paths.map((row) => [JSON.stringify([row.document_id, row.source_locator]), row.category_path]));
  return rows.map((row) => ({ ...row, category_path: row.series === "city"
    ? bySource.get(JSON.stringify([row.document_id, row.source_locator])) || row.category_path
    : row.category_path }));
}

/** Filter availability depends on retained dimensions, not dated price winners.
 * Ordinary parser output normalizes case; differing whitespace spellings of the
 * same quote dimension are rare and retain the exact revision-aware fallback.
 */
export const PRODUCT_FILTER_OPTIONS_SQL = `
  WITH city_dimensions AS MATERIALIZED (
    SELECT DISTINCT m.id AS market_id,m.name AS market_name,
      lower(btrim(r.presentation)) AS presentation_key,r.quantity,
      lower(btrim(r.source_unit)) AS unit_key,
      upper(left(r.presentation,1)) || lower(substr(r.presentation,2)) AS presentation,
      r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) AS units
    FROM regional_price r JOIN market m ON m.name=r.market_name
    WHERE r.product_id=$1 AND ($2='' OR m.region=$2)
      AND r.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
  ), ambiguity AS (
    SELECT EXISTS(SELECT 1 FROM city_dimensions
      GROUP BY market_id,presentation_key,quantity,unit_key HAVING count(*)>1) AS requires_revision_resolution
  ), options AS (
    SELECT DISTINCT
      CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
      m.id AS market_id,m.name AS market_name,'Por unidad de medida'::text AS presentation,
      CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units
    FROM published_price_observation o JOIN market m ON m.id=o.market_id
    WHERE o.product_id=$1 AND ($2='' OR m.region=$2)
      AND o.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
    UNION
    SELECT 'city',market_id,market_name,presentation,units FROM city_dimensions
  ) SELECT options.*,ambiguity.requires_revision_resolution FROM options CROSS JOIN ambiguity
    ORDER BY series,market_name,presentation,units`;

// Preserve separately stored classification corrections and every historical path.
export const PRODUCT_CLASSIFICATIONS_SQL = `
  SELECT DISTINCT c.category_path FROM (
    SELECT DISTINCT document_id,source_locator FROM regional_price
    WHERE product_id=$1 ORDER BY document_id,source_locator
  ) r CROSS JOIN LATERAL (
    SELECT category_path FROM regional_classification c
    WHERE c.document_id=r.document_id AND c.source_locator=r.source_locator OFFSET 0
  ) c ORDER BY c.category_path`;

export type PriceFilters = {
  series?: string;
  market?: string;
  presentation?: string;
  units?: string;
  history?: string;
};
export async function filteredProduct(
  id: string,
  region: string,
  requested: PriceFilters,
) {
  const db = database();
  const product = (await db.query("SELECT * FROM product WHERE id=$1", [id]))
    .rows[0];
  if (!product) return null;
  let options = (await db.query(PRODUCT_FILTER_OPTIONS_SQL, [id, region])).rows;
  if (options.some((option) => option.requires_revision_resolution)) {
    options = (await db.query(
      `WITH quotes AS (${PRICE_QUOTE_VALUES}) SELECT DISTINCT series,market_id,market_name,presentation,units FROM quotes WHERE product_id=$1 AND ($2='' OR region=$2) AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date ORDER BY series,market_name,presentation,units`,
      [id, region],
    )).rows;
  }
  const seriesOptions = [...new Set<string>(options.map((o) => o.series))].sort(
    (a, b) => (a === "city" ? -1 : b === "city" ? 1 : a.localeCompare(b)),
  );
  const series = seriesOptions.includes(requested.series || "")
    ? requested.series!
    : seriesOptions[0] || "monthly";
  const presentations = [
    ...new Set<string>(
      options.filter((o) => o.series === series).map((o) => o.presentation),
    ),
  ];
  const presentation = presentations.some(
    (p) =>
      p.toLocaleLowerCase() ===
      (requested.presentation || "").toLocaleLowerCase(),
  )
    ? presentations.find(
        (p) =>
          p.toLocaleLowerCase() ===
          (requested.presentation || "").toLocaleLowerCase(),
      )!
    : presentations[0] || "";
  const unitOptions = [
    ...new Set<string>(
      options
        .filter((o) => o.series === series && o.presentation === presentation)
        .map((o) => o.units),
    ),
  ];
  const units = unitOptions.includes(requested.units || "")
    ? requested.units!
    : unitOptions[0] || "";
  const market = requested.market || "";
  const historical = requested.history === "all";
  const filter = `product_id=$1 AND ($2='' OR region=$2) AND series=$3 AND presentation=$4 AND units=$5 AND ($6='' OR market_id=$6) AND ${historical ? "observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date" : WINDOW}`;
  const marketIds = [...new Set(options.filter((option) =>
    option.series === series && option.presentation === presentation && option.units === units &&
    (!market || option.market_id === market)).map((option) => option.market_id))];
  const args = [id, region, series, presentation, units, market, marketIds];
  const [quotes, additionalReferences] = await Promise.all([
    db.query(
      `WITH selected AS MATERIALIZED (
        SELECT selected_market_quotes.* FROM unnest($7::text[]) AS selected_market(id)
        CROSS JOIN LATERAL (
          WITH quotes AS (${PRICE_QUOTE_VALUES})
          SELECT * FROM quotes WHERE ${filter} AND market_id=selected_market.id OFFSET 0
        ) selected_market_quotes
      ), latest AS (
        SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date
        FROM selected ORDER BY market_id,observed_on DESC
      ), history AS (
        SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count
        FROM selected GROUP BY observed_on
      ) SELECT
        coalesce((SELECT jsonb_agg(latest ORDER BY market_id) FROM latest),'[]'::jsonb) AS markets,
        coalesce((SELECT jsonb_agg(history ORDER BY date) FROM history),'[]'::jsonb) AS history`,
      args,
    ),
    region ? Promise.resolve([]) : summaryReferencesForProduct(product.name),
  ]);
  const history = quotes.rows[0].history;
  const classifiedMarkets = await withQuoteClassifications(quotes.rows[0].markets);
  const latest = history.at(-1);
  return {
    product,
    markets: classifiedMarkets,
    history,
    current: latest || null,
    classification: currentClassifications(classifiedMarkets, product.category, latest?.date),
    additional_references: additionalReferences,
    filters: {
      region,
      series,
      presentation,
      units,
      market,
      history: historical ? "all" : "recent",
    },
    options: {
      series: seriesOptions,
      presentations,
      units: unitOptions,
      markets: Array.from(
        new Map(
          options.map((o) => [
            o.market_id,
            { id: o.market_id, name: o.market_name },
          ]),
        ).values(),
      ),
    },
  };
}
