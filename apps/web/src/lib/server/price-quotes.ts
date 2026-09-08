import "server-only";
import { database, WINDOW } from "./db";
import { summaryReferencesForProduct } from "./summary-references";

/** Shared quote identities for product filters, maps and market comparisons.
 * City prices are per original package; monthly references keep their base unit.
 * Latest round / publisher revision wins within the same dated quote identity.
 */
export const CITY_PRICE_QUOTES = `
  SELECT product_id,market_id,market_name,city,region,product_name,category,category_path,
    observed_on,(min_price+max_price)/2 AS price,min_price,max_price,unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,document_id,source_locator,source_url,'daily'::text AS period,source_page FROM (
    SELECT DISTINCT ON(r.product_id,m.id,r.observed_on,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)))
      r.*,m.id AS market_id,m.city,m.region,
      coalesce(c.category_path,string_to_array(r.category,' > ')) AS category_path,
      r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) AS units,d.source_url
    FROM regional_price r JOIN market m ON m.name=r.market_name
    JOIN source_document d ON d.id=r.document_id
    LEFT JOIN regional_classification c ON c.document_id=r.document_id AND c.source_locator=r.source_locator
    ORDER BY r.product_id,m.id,r.observed_on,lower(btrim(r.presentation)),r.quantity,lower(btrim(r.source_unit)),r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city`;

export const PRICE_QUOTES = `
  SELECT o.product_id,m.id AS market_id,m.name AS market_name,m.city,m.region,
    p.name AS product_name,p.category,ARRAY[p.category]::text[] AS category_path,
    o.observed_on,o.price,o.min_price,o.max_price,o.unit,
    'Por unidad de medida'::text AS presentation,
    CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
    CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
    o.document_id,o.source_locator,o.source_url,o.period,1::integer AS source_page
  FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
  UNION ALL
${CITY_PRICE_QUOTES}`;

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
  const options = (
    await db.query(
      `WITH quotes AS (${PRICE_QUOTES}) SELECT DISTINCT series,market_id,market_name,presentation,units FROM quotes WHERE product_id=$1 AND ($2='' OR region=$2) AND observed_on<=CURRENT_DATE ORDER BY series,market_name,presentation,units`,
      [id, region],
    )
  ).rows;
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
  const filter = `product_id=$1 AND ($2='' OR region=$2) AND series=$3 AND presentation=$4 AND units=$5 AND ($6='' OR market_id=$6) AND ${historical ? "observed_on<=CURRENT_DATE" : WINDOW}`;
  const args = [id, region, series, presentation, units, market];
  const [markets, history, classification, additionalReferences] = await Promise.all([
    db.query(
      `WITH quotes AS (${PRICE_QUOTES}) SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date FROM quotes WHERE ${filter} ORDER BY market_id,observed_on DESC`,
      args,
    ),
    db.query(
      `WITH quotes AS (${PRICE_QUOTES}) SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count FROM quotes WHERE ${filter} GROUP BY observed_on ORDER BY observed_on`,
      args,
    ),
    db.query(
      `SELECT DISTINCT c.category_path FROM regional_classification c JOIN regional_price r USING(document_id,source_locator) WHERE r.product_id=$1 ORDER BY c.category_path`,
      [id],
    ),
    region ? Promise.resolve([]) : summaryReferencesForProduct(product.name),
  ]);
  const latest = history.rows.at(-1);
  return {
    product,
    markets: markets.rows,
    history: history.rows,
    current: latest || null,
    classification: classification.rows.map((r) => r.category_path),
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
