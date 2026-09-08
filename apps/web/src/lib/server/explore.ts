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
export async function markets(): Promise<Market[]> {
  return (
    await database()
      .query(`WITH quotes AS (${PRICE_QUOTES}) SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN (SELECT market_id,count(DISTINCT product_id) product_count,max(observed_on) date FROM quotes WHERE ${WINDOW} GROUP BY market_id) p ON p.market_id=m.id
    LEFT JOIN (SELECT market_id,max(observed_on) supply_date FROM supply_observation WHERE ${WINDOW} GROUP BY market_id) s ON s.market_id=m.id
    WHERE p.market_id IS NOT NULL OR s.market_id IS NOT NULL ORDER BY product_count DESC,m.name`)
  ).rows;
}
export async function marketDetail(id: string): Promise<MarketDetail | null> {
  const market = (await markets()).find((m) => m.id === id);
  if (!market) return null;
  const products = (
    await database().query(
      `SELECT DISTINCT ON(p.id) p.*,o.price,o.observed_on AS date,o.unit,o.period,o.document_id,o.source_locator,
    NULL AS previous_price,1 AS market_count,CASE WHEN o.source_id='fnc' THEN 'FNC' ELSE 'DANE · SIPSA' END AS source
    FROM published_price_observation o JOIN product p ON p.id=o.product_id WHERE market_id=$1 AND ${WINDOW} ORDER BY p.id,o.observed_on DESC`,
      [id],
    )
  ).rows;
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
  const history = (
    await db.query(
      `SELECT period_start AS date,sum(quantity_kg) quantity_kg FROM supply_observation WHERE ($1='' OR product_id=$1) AND ($2='' OR market_id=$2) AND ${window} GROUP BY period_start ORDER BY period_start`,
      [product, market],
    )
  ).rows;
  const latest_period = history.at(-1)?.date || null;
  const selected_period = history.some((h) => h.date === month)
    ? month
    : latest_period;
  if (!selected_period)
    return { rows: [], history, latest_period, selected_period };
  const rows = (
    await db.query(
      `SELECT s.market_id,m.name market_name,m.region,s.food_id,s.food_name,s.product_id,s.period_start,s.observed_on,s.first_reported_on,s.quantity_kg,s.document_id,s.reporting_days FROM supply_observation s JOIN market m ON m.id=s.market_id WHERE ($1='' OR product_id=$1) AND ($2='' OR market_id=$2) AND period_start=$3 AND ${window} ORDER BY quantity_kg DESC`,
      [product, market, selected_period],
    )
  ).rows;
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
