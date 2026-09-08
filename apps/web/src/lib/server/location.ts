import "server-only";
import { createHash } from "node:crypto";
import { database } from "./db";
import { bogotaToday } from "../planning-math";
import type { Evidence } from "../planning-types";
import type {
  SpatialLayer,
  SpatialReading,
  ForecastGrid,
  ForecastSample,
} from "../location-types";

type Snapshot = {
  id: string;
  source_url: string;
  fetched_at: string;
  records: Record<string, unknown>[];
  metadata: Record<string, unknown>;
  content: Buffer;
  title: string;
  publisher: string;
  reference_period: string;
};
const pending = new Map<string, Promise<unknown>>();
async function single<T>(key: string, run: () => Promise<T>): Promise<T> {
  if (pending.has(key)) return pending.get(key) as Promise<T>;
  const task = run().finally(() => pending.delete(key));
  pending.set(key, task);
  return task;
}
async function cached(key: string, hours: number): Promise<Snapshot | null> {
  return (
    (
      await database().query<Snapshot>(
        "SELECT * FROM spatial_snapshot WHERE cache_key=$1 AND fetched_at>now()-($2::float*interval '1 hour') ORDER BY fetched_at DESC LIMIT 1",
        [key, hours],
      )
    ).rows[0] || null
  );
}
async function archive(
  key: string,
  title: string,
  publisher: string,
  url: string,
  period: string,
  response: unknown,
  records: Record<string, unknown>[],
  metadata: Record<string, unknown> = {},
) {
  // The downloaded archive includes the exact query URL and parsed source response.
  const content = Buffer.from(
    JSON.stringify({ consulta: url, respuesta: response }),
  );
  const id = createHash("sha256").update(content).digest("hex");
  await database().query(
    "INSERT INTO spatial_snapshot(id,cache_key,title,publisher,source_url,reference_period,content,records,metadata) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(id) DO NOTHING",
    [
      id,
      key,
      title,
      publisher,
      url,
      period,
      content,
      JSON.stringify(records),
      JSON.stringify({ ...metadata, envelope: true }),
    ],
  );
  return (
    await database().query<Snapshot>(
      "SELECT * FROM spatial_snapshot WHERE id=$1",
      [id],
    )
  ).rows[0];
}
export async function spatialLayers(): Promise<SpatialLayer[]> {
  return (
    await database().query("SELECT definition FROM spatial_layer ORDER BY id")
  ).rows.map((r) => r.definition);
}
export async function spatialLayer(id: string): Promise<SpatialLayer | null> {
  return (
    (
      await database().query(
        "SELECT definition FROM spatial_layer WHERE id=$1",
        [id],
      )
    ).rows[0]?.definition || null
  );
}
export function monthFilter(layer: SpatialLayer, month: number) {
  if (!layer.monthly) return "1=1";
  const y = layer.monthYear!;
  const start = `${y}-${String(month).padStart(2, "0")}-01`;
  const end =
    month === 12
      ? `${y + 1}-01-01`
      : `${y}-${String(month + 1).padStart(2, "0")}-01`;
  return `${layer.monthField} >= date '${start}' AND ${layer.monthField} < date '${end}'`;
}
async function remote(url: string) {
  const res = await fetch(url, {
    signal: AbortSignal.timeout(25000),
    cache: "no-store",
  });
  if (!res.ok) throw Error("La entidad no respondió a la consulta.");
  const body = await res.json();
  if (body.error) throw Error("El geoservicio no pudo resolver esta consulta.");
  return body;
}
export async function spatialPoint(
  layer: SpatialLayer,
  latitude: number,
  longitude: number,
  month: number,
): Promise<SpatialReading> {
  // Six decimal places retain the explicitly selected point, without municipality snapping.
  const lat = latitude.toFixed(6),
    lon = longitude.toFixed(6),
    key = `point:${layer.id}:${month}:${lat}:${lon}`;
  return single(key, async () => {
    let row = await cached(key, 24 * 30);
    if (!row) {
      const url = new URL(`${layer.service}/${layer.layer}/query`);
      url.search = new URLSearchParams({
        f: "json",
        where: monthFilter(layer, month),
        geometry: `${lon},${lat}`,
        geometryType: "esriGeometryPoint",
        inSR: "4326",
        spatialRel: "esriSpatialRelIntersects",
        outFields: "*",
        returnGeometry: "false",
        resultRecordCount: "30",
      }).toString();
      const payload = await remote(url.toString());
      if (payload.exceededTransferLimit)
        throw Error("Hay demasiadas unidades superpuestas en este punto.");
      const schema = (
        await database().query(
          "SELECT metadata FROM spatial_snapshot WHERE id=$1",
          [layer.documentId.slice(8)],
        )
      ).rows[0]?.metadata?.schema;
      const fields =
        (schema?.fields as {
          name: string;
          alias: string;
          domain?: { codedValues?: { code: unknown; name: string }[] };
        }[]) || [];
      const records = (payload.features || []).map(
        (feature: { attributes: Record<string, unknown> }) => {
          const values: Record<string, unknown> = {
            latitud: latitude,
            longitud: longitude,
            periodo: layer.period,
            ...(layer.monthly ? { mes: month } : {}),
          };
          values.registro_original =
            feature.attributes.objectid ?? feature.attributes.OBJECTID;
          for (const name of layer.valueFields) {
            const field = fields.find((f) => f.name === name);
            const raw = feature.attributes[name];
            const decoded = field?.domain?.codedValues?.find(
              (v) => v.code === raw,
            )?.name;
            values[name] = decoded ?? raw ?? null;
          }
          return values;
        },
      );
      row = await archive(
        key,
        `${layer.title} — consulta en ${lat}, ${lon}`,
        layer.publisher,
        url.toString(),
        layer.period,
        payload,
        records,
        {
          note: layer.note,
          parents: [layer.documentId],
          empty: records.length === 0,
        },
      );
    }
    return {
      documentId: "spatial-" + row.id,
      fetchedAt: row.fetched_at,
      records: row.records,
      sourceUrl: row.source_url,
    };
  });
}
export async function forecastGrid(
  latitude: number,
  longitude: number,
  step: number,
): Promise<ForecastGrid> {
  const lat = Math.round(latitude / step) * step,
    lon = Math.round(longitude / step) * step,
    key = `forecast:${lat.toFixed(3)}:${lon.toFixed(3)}:${step}`;
  return single(key, async () => {
    let row = await cached(key, 2);
    if (
      row &&
      (row.metadata.samples as ForecastSample[])?.[0]?.dates[0] !==
        bogotaToday()
    )
      row = null;
    if (!row) {
      const points: { latitude: number; longitude: number }[] = [];
      for (let y = -2; y <= 2; y++)
        for (let x = -2; x <= 2; x++) {
          const p = {
            latitude: +(lat + y * step).toFixed(3),
            longitude: +(lon + x * step).toFixed(3),
          };
          if (
            p.latitude >= -5 &&
            p.latitude <= 14 &&
            p.longitude >= -82 &&
            p.longitude <= -66
          )
            points.push(p);
        }
      if (!points.length) throw Error("Acerca el mapa a Colombia.");
      const u = new URL(
        process.env.OPEN_METEO_API_KEY
          ? "https://customer-api.open-meteo.com/v1/forecast"
          : "https://api.open-meteo.com/v1/forecast",
      );
      u.search = new URLSearchParams({
        latitude: points.map((p) => p.latitude).join(","),
        longitude: points.map((p) => p.longitude).join(","),
        daily:
          "precipitation_sum,temperature_2m_max,temperature_2m_min,wind_speed_10m_max",
        timezone: "America/Bogota",
        forecast_days: "7",
        wind_speed_unit: "kmh",
        temperature_unit: "celsius",
        precipitation_unit: "mm",
      }).toString();
      const publicUrl = u.toString();
      if (process.env.OPEN_METEO_API_KEY)
        u.searchParams.set("apikey", process.env.OPEN_METEO_API_KEY);
      const payload = await remote(u.toString());
      const results = Array.isArray(payload) ? payload : [payload];
      if (results.length !== points.length)
        throw Error("El pronóstico regional llegó incompleto.");
      const samples: ForecastSample[] = results.map((r, i) => {
        if (
          r.daily?.time?.length !== 7 ||
          ![
            "precipitation_sum",
            "temperature_2m_max",
            "temperature_2m_min",
            "wind_speed_10m_max",
          ].every(
            (k) =>
              Array.isArray(r.daily[k]) &&
              r.daily[k].length === 7 &&
              r.daily[k].every(
                (v: unknown) =>
                  v === null || (typeof v === "number" && Number.isFinite(v)),
              ),
          ) ||
          r.daily_units?.precipitation_sum !== "mm" ||
          r.daily_units?.wind_speed_10m_max !== "km/h" ||
          r.daily_units?.temperature_2m_max !== "°C"
        )
          throw Error("Las unidades del pronóstico cambiaron.");
        return {
          ...points[i],
          modelLatitude: r.latitude,
          modelLongitude: r.longitude,
          dates: r.daily.time,
          rain: r.daily.precipitation_sum,
          high: r.daily.temperature_2m_max,
          low: r.daily.temperature_2m_min,
          wind: r.daily.wind_speed_10m_max,
        };
      });
      row = await archive(
        key,
        "Pronóstico regional — puntos de consulta",
        "Open-Meteo",
        publicUrl,
        `${samples[0].dates[0]} a ${samples[0].dates.at(-1)}`,
        payload,
        samples.map((p) => ({
          latitud_consultada: p.latitude,
          longitud_consultada: p.longitude,
          latitud_modelo: p.modelLatitude,
          longitud_modelo: p.modelLongitude,
          fechas: p.dates,
          lluvia_mm: p.rain,
          maxima_C: p.high,
          minima_C: p.low,
          viento_kmh: p.wind,
        })),
        {
          samples,
          step,
          note: "Puntos muestreados del modelo; no mediciones. La separación de puntos no es la resolución del modelo. AgroAmigo señala atención si cualquier día tiene lluvia ≥20 mm, viento ≥40 km/h, máxima ≥35 °C o mínima ≤2 °C. Son umbrales orientativos, no alertas oficiales ni probabilidades de daño.",
        },
      );
    }
    return {
      documentId: "spatial-" + row.id,
      fetchedAt: row.fetched_at,
      samples: row.metadata.samples as ForecastSample[],
      step,
      stale: Date.now() - new Date(row.fetched_at).getTime() > 2 * 3600000,
    };
  });
}
export async function spatialEvidence(id: string): Promise<Evidence | null> {
  const r = (
    await database().query<Snapshot>(
      "SELECT * FROM spatial_snapshot WHERE id=$1",
      [id.slice(8)],
    )
  ).rows[0];
  if (!r) return null;
  const parents = Array.isArray(r.metadata.parents)
    ? (r.metadata.parents as string[])
    : [];
  const parentRows = parents.length
    ? (
        await database().query(
          "SELECT id,title FROM spatial_snapshot WHERE id=ANY($1::text[])",
          [parents.map((id) => id.slice(8))],
        )
      ).rows
    : [];
  return {
    id,
    title: r.title,
    publisher: r.publisher,
    source_url: r.source_url,
    reference_period: r.reference_period,
    retrieved_at: r.fetched_at,
    media_type: "application/json",
    kind: r.metadata.envelope ? "extract" : "original",
    bytes: r.content.length,
    page_count: null,
    metadata: r.metadata,
    records: r.records.length
      ? r.records
      : [
          {
            resultado:
              "La fuente no devolvió una unidad cartográfica para este punto. Esto no significa ausencia de amenaza ni suelo apto.",
          },
        ],
    parents: parentRows.map((p) => ({ id: "spatial-" + p.id, title: p.title })),
  };
}
export async function spatialContent(id: string) {
  return (
    await database().query("SELECT content FROM spatial_snapshot WHERE id=$1", [
      id.slice(8),
    ])
  ).rows[0]?.content as Buffer | undefined;
}
