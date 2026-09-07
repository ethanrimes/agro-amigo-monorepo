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
export async function markets(): Promise<Market[]> {
  return (
    await database().query(`SELECT m.*,u.latitude,u.longitude,u.department_id,
    coalesce(p.product_count,0) AS product_count,p.date,s.supply_date
    FROM market m LEFT JOIN municipality u ON u.id=m.municipality_id
    LEFT JOIN (SELECT market_id,count(DISTINCT product_id) product_count,max(observed_on) date FROM price_observation WHERE ${WINDOW} GROUP BY market_id) p ON p.market_id=m.id
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
    FROM price_observation o JOIN product p ON p.id=o.product_id WHERE market_id=$1 AND ${WINDOW} ORDER BY p.id,o.observed_on DESC`,
      [id],
    )
  ).rows;
  return { market, products };
}
export async function inputDetail(
  id: string,
  department: string,
): Promise<InputDetail | null> {
  const db = database();
  const regions = (await inputs("")).filter((r) => r.id === id);
  if (!regions.length) return null;
  const input = regions.find((r) => r.department === department) || regions[0];
  const history = (
    await db.query(
      `SELECT observed_on AS date,price FROM input_price WHERE id=$1 AND department=$2 AND ${WINDOW} ORDER BY observed_on`,
      [id, input.department],
    )
  ).rows;
  return { input, regions, history };
}
export async function supply(
  product: string,
  market: string,
  month: string,
): Promise<SupplyData> {
  const db = database();
  const history = (
    await db.query(
      `SELECT period_start AS date,sum(quantity_kg) quantity_kg FROM supply_observation WHERE ($1='' OR product_id=$1) AND ($2='' OR market_id=$2) AND ${WINDOW} GROUP BY period_start ORDER BY period_start`,
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
      `SELECT s.market_id,m.name market_name,m.region,s.food_id,s.food_name,s.product_id,s.period_start,s.observed_on,s.first_reported_on,s.quantity_kg,s.document_id,s.reporting_days FROM supply_observation s JOIN market m ON m.id=s.market_id WHERE ($1='' OR product_id=$1) AND ($2='' OR market_id=$2) AND period_start=$3 AND ${WINDOW} ORDER BY quantity_kg DESC`,
      [product, market, selected_period],
    )
  ).rows;
  return { rows, history, latest_period, selected_period };
}
export async function mapData(
  kind: string,
  id: string,
  mode: string,
): Promise<MapData> {
  const db = database();
  let points: MapPoint[] = [];
  let unit = "referencias";
  if (kind === "input") {
    unit = "COP / presentación";
    const rows = (
      await db.query(
        `SELECT DISTINCT ON(department) department,price,observed_on AS date,document_id FROM input_price WHERE id=$1 AND ${WINDOW} ORDER BY department,observed_on DESC`,
        [id],
      )
    ).rows;
    const places = (
      await db.query(
        `SELECT DISTINCT ON(department_id) department_id,department,latitude,longitude FROM municipality ORDER BY department_id,id`,
      )
    ).rows;
    const fold = (s: string) =>
      s
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase();
    points = rows.flatMap((r) => {
      const p = places.find((p) => fold(p.department) === fold(r.department));
      return p
        ? [
            {
              id: p.department_id,
              name: r.department,
              region: r.department,
              department_id: p.department_id,
              latitude: p.latitude,
              longitude: p.longitude,
              value: r.price,
              date: r.date,
              unit,
              document_id: r.document_id,
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
    points = (
      await db.query(
        `SELECT m.id,m.name,m.region,u.department_id,u.latitude,u.longitude,o.price AS value,o.observed_on AS date,CASE WHEN o.unit='125kg' THEN 'COP / carga 125 kg' ELSE 'COP / kg' END AS unit,o.document_id FROM price_observation o JOIN market m ON m.id=o.market_id JOIN municipality u ON u.id=m.municipality_id WHERE o.product_id=$1 AND ${WINDOW} AND o.observed_on=(SELECT max(observed_on) FROM price_observation WHERE product_id=$1 AND ${WINDOW})`,
        [id],
      )
    ).rows;
    unit = points[0]?.unit || "COP / kg";
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
    points,
    unit,
    date: points.reduce<string | null>(
      (a, p) => (!a || p.date > a ? p.date : a),
      null,
    ),
    basis:
      kind === "input"
        ? "Promedios departamentales por la misma presentación."
        : mode === "supply"
          ? "Llegadas reportadas en el último mes disponible; no son inventario para comprar."
          : id
            ? "Precios del mismo producto y fecha; ubicaciones municipales de referencia."
            : "Mercados con información; ubicaciones municipales de referencia.",
  };
}
