import "server-only";
import { normalizeLabel } from "../label-normalization";
import { database, WINDOW } from "./db";
import type {
  Market,
  MarketDetail,
  InputDetail,
  InputAliasChoice,
  SupplyData,
  MapData,
  MapPoint,
} from "../explore-types";
import { inputs } from "./planning";
import { PRICE_QUOTES, filteredProduct } from "./price-quotes";
import { departmentKey, departmentVariants } from "../filter-labels";
import { municipalityKey, municipalityLabel } from "../input-locations";
import { assertInputIdentityMembers, assertNoLatestInputIdentityConflicts, inputLocationOptions, latestEquivalentInputRows, resolveInputIdentity } from "../input-identity-equivalence";
import { pdfLocationPage } from "../pdf-locator";
import type { MapFilters } from "../explore-types";
import { supplyQueries, supplyMapQuery } from "./supply-sql";
import { marketsQuery, marketDetailQuery, marketProductsQuery } from "./market-sql";
import { resolveMarketAlias } from "./market-alias";
export async function markets(): Promise<Market[]> {
  return (await database().query(marketsQuery(WINDOW))).rows;
}
export async function marketDetail(id: string): Promise<MarketDetail | null> {
  const db = database();
  id = await resolveMarketAlias(db, id);
  const market = (await db.query(marketDetailQuery(WINDOW), [id])).rows[0];
  if (!market) return null;
  const products = (await db.query(marketProductsQuery(WINDOW), [id])).rows;
  return { market, products };
}
export async function inputDetail(
  id: string,
  department: string,
  scope = "department",
  municipality = "",
  historical = false,
): Promise<InputDetail | null> {
  const db = database();
  const identity = resolveInputIdentity(id);
  const nativeRegions = await inputs("", scope, historical, id, false);
  assertInputIdentityMembers(nativeRegions, identity.memberIds);
  const latestRows = latestEquivalentInputRows(nativeRegions);
  const regions = inputLocationOptions(latestRows);
  if (!regions.length) return null;
  const input = regions.filter(
    (r) =>
      (!department || departmentKey(r.department) === departmentKey(department)) &&
      (!municipality || municipalityKey(r.municipality) === municipalityKey(municipality)),
  ).sort((a, b) => b.observed_on.localeCompare(a.observed_on) ||
    String(a.source_locator || a.document_id).localeCompare(String(b.source_locator || b.document_id)))[0];
  if (!input) return null;
  const currentQuotes = latestRows.filter((row) =>
    departmentKey(row.department) === departmentKey(input.department) &&
    municipalityKey(row.municipality) === municipalityKey(input.municipality) &&
    row.observed_on === input.observed_on,
  );
  const municipal = scope === "municipality";
  const nativeMunicipalities = municipal ? [...new Set(nativeRegions.filter((row) =>
    identity.memberIds.includes(String(row.source_input_id || row.id)) && departmentKey(row.department) === departmentKey(input.department) &&
    municipalityKey(row.municipality) === municipalityKey(input.municipality),
  ).map((row) => row.municipality))] : [];
  const historyRows = (await db.query(
    `SELECT id,name,category,presentation,brand,registration,product_line,observed_on AS date,price,document_id,source_locator,department${municipal ? ",municipality" : ""} FROM ${municipal ? "published_input_municipal_price" : "published_input_price"} WHERE id=ANY($1::text[]) AND department=ANY($2::text[]) ${municipal ? "AND municipality=ANY($3::text[])" : ""} AND ${historical ? "observed_on<=CURRENT_DATE" : WINDOW} ORDER BY observed_on,price DESC,source_locator`,
      municipal
        ? [identity.memberIds, departmentVariants(input.department), nativeMunicipalities]
        : [identity.memberIds, departmentVariants(input.department)],
    )).rows;
  assertInputIdentityMembers(historyRows, identity.memberIds);
  const history = historyRows.map((row) => ({
    observation_id: JSON.stringify([row.id,row.document_id,row.source_locator,row.date,row.price]),
    date: row.date,
    price: row.price,
    sources: [{
      source_input_id: row.id,
      source_name: row.name,
      document_id: row.document_id,
      source_locator: row.source_locator,
      source_page: pdfLocationPage(row.source_locator) || null,
      market_id: municipal ? JSON.stringify([row.department, row.municipality]) : row.department,
      market_name: municipal ? `${row.municipality}, ${row.department}` : row.department,
    }],
  }));
  return { input, regions, history, current_quotes: currentQuotes };
}
export async function inputAliases(
  legacyId: string,
  department: string,
  scope = "department",
  municipality = "",
): Promise<InputAliasChoice[]> {
  if (!legacyId) return [];
  const municipal = scope === "municipality";
  const table = municipal
    ? "published_input_municipal_price"
    : "published_input_price";
  try {
    const departments = departmentVariants(department);
    const discovered = municipal && municipality
      ? (await database().query<{ municipality: string }>(
          `SELECT DISTINCT p.municipality FROM input_identity_alias a JOIN input_municipal_price p
           ON p.id=a.id WHERE a.legacy_id=$1 AND p.department=ANY($2::text[])
           ORDER BY p.municipality`, [legacyId, departments],
        )).rows.map((row) => row.municipality)
          .filter((name) => municipalityKey(name) === municipalityKey(municipality))
      : [];
    const nativeMunicipalities = municipality
      ? [...new Set([municipality, ...discovered])] : [];
    return (
      await database().query<InputAliasChoice>(
        `WITH choices AS (
          SELECT p.id,p.name,p.presentation,p.product_line,p.brand,
            p.department,${municipal ? "p.municipality" : "''::text AS municipality"},
            p.price,p.observed_on,
            row_number() OVER (PARTITION BY p.id ORDER BY p.observed_on DESC) AS rank
          FROM input_identity_alias a JOIN ${table} p ON p.id=a.id
          WHERE a.legacy_id=$1 AND p.observed_on<=CURRENT_DATE
            AND (cardinality($2::text[])=0 OR p.department=ANY($2::text[]))
            ${municipal ? "AND (cardinality($3::text[])=0 OR p.municipality=ANY($3::text[]))" : ""}
        )
        SELECT id,name,presentation,product_line,brand,department,municipality,price,observed_on
        FROM choices WHERE rank=1
        ORDER BY product_line,presentation,id LIMIT 40`,
        municipal
          ? [legacyId, departments, nativeMunicipalities]
          : [legacyId, departments],
      )
    ).rows;
  } catch (error) {
    // Web and worker releases can overlap briefly while the additive alias
    // migration is installing. Existing input detail pages remain usable.
    if ((error as { code?: string }).code === "42P01") return [];
    throw error;
  }
}
export async function supply(
  product: string,
  market: string,
  month: string,
  historical = false,
): Promise<SupplyData> {
  const db = database();
  const window = historical ? "observed_on<=CURRENT_DATE" : WINDOW;
  const queries = supplyQueries(product, market, window);
  const history = (await db.query(queries.history)).rows;
  const latest_period = history.at(-1)?.date || null;
  const selected_period = history.some((h) => h.date === month)
    ? month
    : latest_period;
  if (!selected_period)
    return { rows: [], history, latest_period, selected_period };
  const rows = (await db.query(queries.month(selected_period))).rows;
  return { rows, history, latest_period, selected_period };
}
export async function mapData(
  kind: string,
  id: string,
  mode: string,
  filters: MapFilters = {},
): Promise<MapData> {
  const db = database();
  let points: MapPoint[] = [];
  let unit = "referencias";
  let resolved: Pick<MapData, "filters" | "options" | "selection_label"> = {};
  if (kind === "input") {
    const municipal = filters.scope === "municipality";
    const scope = municipal ? "municipality" : "department";
    const nativeRows = id
      ? await inputs(
            filters.region || "",
            scope,
            filters.history === "all",
            id,
            false,
          )
      : [];
    if (id) assertInputIdentityMembers(nativeRows, resolveInputIdentity(id).memberIds);
    const rows = latestEquivalentInputRows(nativeRows.filter(
          (r) =>
            !municipal ||
            !filters.municipality ||
            municipalityKey(r.municipality) === municipalityKey(filters.municipality),
        ));
    if (id) assertNoLatestInputIdentityConflicts(rows);
    unit = "COP / " + (rows[0]?.presentation || "presentación");
    resolved = {
      selection_label: rows[0]
        ? [rows[0].name, rows[0].presentation, rows[0].product_line && `Línea: ${rows[0].product_line}`]
            .filter(Boolean).join(" · ")
        : undefined,
      filters: {
        ...filters,
        scope,
        history: filters.history === "all" ? "all" : "recent",
        presentation: rows[0]?.presentation || "",
      },
    };
    const places = (
      await db.query(
        `SELECT id,name,department_id,department,latitude,longitude FROM municipality ORDER BY id`,
      )
    ).rows;
    points = rows.flatMap((r) => {
      const candidates = places.filter(
        (p) =>
          departmentKey(p.department) === departmentKey(r.department) &&
          (!municipal || municipalityKey(p.name) === municipalityKey(r.municipality)),
      );
      const p = candidates[0];
      return p && p.latitude !== null && p.longitude !== null
        ? [
            {
              id: municipal ? p.id : p.department_id,
              name: municipal
                ? municipalityLabel(r.municipality) + ", " + r.department
                : r.department,
              region: r.department,
              department_id: p.department_id,
              latitude: Number(p.latitude),
              longitude: Number(p.longitude),
              value: r.price,
              date: r.observed_on,
              unit,
              document_id: r.document_id,
              source_locator: r.source_locator,
              ...(r.source_input_id ? {
                quote_key: JSON.stringify([r.source_input_id,r.document_id,r.source_locator,r.observed_on,r.price]),
                input_id: r.id,
                source_input_id: r.source_input_id,
                source_name: r.source_name,
              } : {}),
              presentation: r.presentation,
              municipality: municipal ? r.municipality : undefined,
            },
          ]
        : [];
    });
  } else if (mode === "supply") {
    unit = "kg";
    points = (await db.query(supplyMapQuery(id,
      departmentVariants(filters.region || ""),
      filters.history === "all" ? "observed_on<=CURRENT_DATE" : WINDOW,
    ))).rows;
    resolved = { filters: { region: filters.region || "", history: filters.history === "all" ? "all" : "recent" } };
  } else if (id) {
    const detail = await filteredProduct(id, filters.region || "", filters);
    if (detail) {
      resolved = { filters: detail.filters, options: detail.options, selection_label: detail.product.name };
      unit = `COP / ${normalizeLabel(detail.filters.presentation, "presentation")} · ${detail.filters.units}`;
      const locationRows = (
        await db.query(
          `SELECT m.id AS market_id,m.city,m.region,m.municipality_id,
                  u.id AS resolved_municipality_id,u.name AS municipality_name,
                  u.department AS municipality_department,u.department_id,
                  u.latitude,u.longitude
           FROM market m
           LEFT JOIN municipality u ON
             (m.municipality_id IS NOT NULL AND u.id=m.municipality_id)
             OR (m.municipality_id IS NULL
                 AND (m.id LIKE 'finca-%' OR m.id LIKE 'molino-%')
                 AND lower(btrim(u.department))=lower(btrim(m.region)))
           WHERE m.id=ANY($1::text[])
           ORDER BY m.id,u.id`,
          [detail.markets.map((m) => m.id)],
        )
      ).rows;
      const locationsByMarket = new Map<string, typeof locationRows>();
      for (const row of locationRows) {
        locationsByMarket.set(row.market_id, [
          ...(locationsByMarket.get(row.market_id) || []), row,
        ]);
      }
      points = detail.markets.flatMap((m) => {
        const rows = locationsByMarket.get(m.id) || [];
        const specialMarket =
          (m.series === "farmgate" && m.id.startsWith("finca-")) ||
          (m.series === "mill" && m.id.startsWith("molino-"));
        if (!specialMarket) {
          // Preserve the historical direct-link behavior for ordinary city
          // markets; their literal display names need not equal the official
          // municipality label (for example, Cali / Santiago de Cali).
          const direct = rows.find((row) =>
            row.municipality_id !== null &&
            row.resolved_municipality_id === row.municipality_id,
          );
          return direct && direct.latitude !== null && direct.longitude !== null
            ? [{
                id: direct.market_id,
                department_id: direct.department_id,
                latitude: Number(direct.latitude),
                longitude: Number(direct.longitude),
                name: m.name,
                region: m.region,
                value: m.price,
                date: m.date,
                unit,
                document_id: m.document_id,
                source_page: m.source_page,
                source_locator: m.source_locator,
                presentation: m.presentation,
                units: m.units,
                series: m.series,
                min_price: m.min_price,
                max_price: m.max_price,
              }]
            : [];
        }
        const linked = rows.find((row) =>
          row.municipality_id !== null &&
          row.resolved_municipality_id &&
          departmentKey(row.municipality_department || "") === departmentKey(m.region) &&
          municipalityKey(row.municipality_name || "") === municipalityKey(row.city || ""),
        );
        const candidates = linked
          ? [linked]
          : rows.filter((row) =>
              row.resolved_municipality_id &&
              departmentKey(row.municipality_department || "") === departmentKey(m.region) &&
              municipalityKey(row.municipality_name || "") === municipalityKey(row.city || ""),
            );
        const uniqueCandidates = new Map(
          candidates.map((row) => [row.resolved_municipality_id, row]),
        );
        const place = uniqueCandidates.size === 1
          ? [...uniqueCandidates.values()][0]
          : undefined;
        return place && place.latitude !== null && place.longitude !== null
          ? [
              {
                id: place.market_id,
                department_id: place.department_id,
                latitude: Number(place.latitude),
                longitude: Number(place.longitude),
                name: m.name,
                region: m.region,
                value: m.price,
                date: m.date,
                unit,
                document_id: m.document_id,
                source_page: m.source_page,
                source_locator: m.source_locator,
                presentation: m.presentation,
                units: m.units,
                series: m.series,
                min_price: m.min_price,
                max_price: m.max_price,
              },
            ]
          : [];
      });
    }
  } else {
    points = (await markets())
      .filter((m) => m.latitude !== null && m.longitude !== null)
      .map((m) => ({
        id: m.id,
        name: m.name,
        region: m.region,
        department_id: m.department_id!,
        latitude: m.latitude!,
        longitude: m.longitude!,
        value: m.product_count,
        date: m.date || m.supply_date || "",
        unit: "productos con precio",
      }));
    unit = "productos con precio";
  }
  return {
    ...resolved,
    ...(mode === "supply" ? { period_start: points[0]?.period_start || null } : {}),
    points,
    unit,
    date: points.reduce<string | null>(
      (a, p) => (!a || p.date > a ? p.date : a),
      null,
    ),
    basis:
      kind === "input"
        ? filters.scope === "municipality"
          ? "Precios municipales de la misma presentación; los puntos representan cabeceras municipales."
          : "Promedios departamentales de la misma presentación; las áreas representan la cobertura del precio."
        : mode === "supply"
          ? "Llegadas reportadas en el último mes disponible; no son inventario para comprar."
          : id && resolved.filters?.series === "city"
            ? "Punto medio calculado entre el mínimo y máximo de la última ronda publicada, por mercado y para el mismo producto, presentación y unidades. No es un promedio publicado por DANE. Cada cotización conserva su fecha; los puntos indican el municipio."
            : id
            ? "Último precio por mercado con el mismo producto, presentación y unidades. Cada cotización muestra su fecha; las coordenadas son una referencia municipal y no indican la ubicación de una finca."
            : "Mercados con información; ubicaciones municipales de referencia.",
  };
}
