import "server-only";
import { database, WINDOW } from "./db";
import type {
  Market,
  MarketDetail,
  InputDetail,
  SupplyData,
  MapData,
  MapPoint,
} from "../explore-types";
import { inputs } from "./planning";
import { PRICE_QUOTES, filteredProduct } from "./price-quotes";
import type { MapFilters } from "../explore-types";
import { supplyQueries } from "./supply-sql";
import { marketsQuery, marketDetailQuery, marketProductsQuery } from "./market-sql";
export async function markets(): Promise<Market[]> {
  return (await database().query(marketsQuery(WINDOW))).rows;
}
export async function marketDetail(id: string): Promise<MarketDetail | null> {
  const market = (await database().query(marketDetailQuery(WINDOW), [id])).rows[0];
  if (!market) return null;
  const products = (await database().query(marketProductsQuery(WINDOW), [id])).rows;
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
  const regions = await inputs("", scope, historical, id, false);
  if (!regions.length) return null;
  const input =
    regions.find(
      (r) =>
        r.department === department &&
        (!municipality || r.municipality === municipality),
    ) || regions[0];
  const municipal = scope === "municipality";
  const history = (
    await db.query(
      `SELECT observed_on AS date,price FROM ${municipal ? "published_input_municipal_price" : "published_input_price"} WHERE id=$1 AND department=$2 ${municipal ? "AND municipality=$3" : ""} AND ${historical ? "observed_on<=CURRENT_DATE" : WINDOW} ORDER BY observed_on`,
      municipal
        ? [id, input.department, input.municipality]
        : [id, input.department],
    )
  ).rows;
  return { input, regions, history };
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
    const rows = id
      ? (
          await inputs(
            filters.region || "",
            scope,
            filters.history === "all",
            id,
            false,
          )
        ).filter(
          (r) =>
            !municipal ||
            !filters.municipality ||
            r.municipality === filters.municipality,
        )
      : [];
    unit = "COP / " + (rows[0]?.presentation || "presentación");
    resolved = {
      selection_label: rows[0]
        ? rows[0].name + " · " + rows[0].presentation
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
    const fold = (s: string) =>
      s
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
    points = rows.flatMap((r) => {
      const candidates = places.filter(
        (p) =>
          fold(p.department) === fold(r.department) &&
          (!municipal || fold(p.name) === fold(r.municipality)),
      );
      const p = candidates[0];
      return p && p.latitude !== null && p.longitude !== null
        ? [
            {
              id: municipal ? p.id : p.department_id,
              name: municipal
                ? r.municipality + ", " + r.department
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
              presentation: r.presentation,
            },
          ]
        : [];
    });
  } else if (mode === "supply") {
    unit = "kg";
    points = (
      await db.query(
        `SELECT m.id,m.name,m.region,u.department_id,u.latitude,u.longitude,sum(s.quantity_kg) AS value,max(s.observed_on) AS date,'kg' AS unit FROM supply_observation s JOIN market m ON m.id=s.market_id JOIN municipality u ON u.id=m.municipality_id WHERE ($1='' OR s.product_id=$1) AND s.period_start=(SELECT max(period_start) FROM supply_observation WHERE ($1='' OR product_id=$1) AND ${WINDOW}) AND ${WINDOW} GROUP BY m.id,u.id`,
        [id],
      )
    ).rows;
  } else if (id) {
    const detail = await filteredProduct(id, filters.region || "", filters);
    if (detail) {
      resolved = { filters: detail.filters, options: detail.options };
      unit = `COP / ${detail.filters.presentation} · ${detail.filters.units}`;
      const places = (
        await db.query(
          `SELECT m.id,u.department_id,u.latitude,u.longitude FROM market m JOIN municipality u ON u.id=m.municipality_id WHERE m.id=ANY($1::text[])`,
          [detail.markets.map((m) => m.id)],
        )
      ).rows;
      points = detail.markets.flatMap((m) => {
        const place = places.find((p) => p.id === m.id);
        return place && place.latitude !== null && place.longitude !== null
          ? [
              {
                ...place,
                name: m.name,
                region: m.region,
                value: m.price,
                date: m.date,
                unit,
                document_id: m.document_id,
                source_page: m.source_page,
                presentation: m.presentation,
                units: m.units,
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
          : id
            ? "Último precio por mercado con el mismo producto, presentación y unidades. Cada cotización muestra su fecha; los puntos indican el municipio."
            : "Mercados con información; ubicaciones municipales de referencia.",
  };
}
