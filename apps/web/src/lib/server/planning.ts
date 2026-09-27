import "server-only";
import { OFFICIAL_EVIDENCE_ROWS_SQL } from "./official-evidence-sql";
import { createHash } from "node:crypto";
import { reconcileInputCatalog } from "./input-identities";
import { database, WINDOW } from "./db";
import type {
  Evidence,
  FarmData,
  Municipality,
  Weather,
  Seasonality,
} from "../planning-types";
import { fold } from "../planning-math";
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
    latest: latest.rows[0] || null,
    years: years.rows,
    unit: coffee ? "kg de pergamino seco" : latest.rows[0]?.unit || "kg",
    method:
      "Para cada año completo se divide el precio del mes objetivo por el precio del mes de referencia, en el mismo mercado y producto. Se aplican los percentiles 25, 50 y 75 de esas razones al precio reciente. Mínimo 3 años completos. Valores nominales; no es un pronóstico de venta ni incorpora inflación futura.",
  };
}
/** Catalog reads select a winner before loading its previous-month price.
 * Detail reads retain a separate newest quote for every exact location.
 */
async function readInputRows(
  department: string,
  scope = "department",
  historical = false,
  id = "",
  grouped = false,
) {
  const municipal = scope === "municipality";
  const table = municipal ? "input_municipal_price" : "input_price";
  const period = historical ? "observed_on<=CURRENT_DATE" : WINDOW;
  if (grouped && department && !municipal && !historical) {
    // Read the department's recent published quotes once. The department-leading
    // covering index avoids a separate random lookup for each current/prior price.
    // Keep the last observation in each calendar month before finding its
    // predecessor: two quotes in the current month must not hide last month's.
    const query = `WITH available AS MATERIALIZED (
        SELECT p.* FROM published_input_price p
        WHERE ${period} AND p.department=$1 AND ($2='' OR p.id=$2)
      ), months AS (
        SELECT DISTINCT ON(id,date_trunc('month',observed_on)) * FROM available
        ORDER BY id,date_trunc('month',observed_on) DESC,observed_on DESC,price
      ), history AS (
        SELECT m.*,lead(price) OVER month_order AS prior_price,
          lead(observed_on) OVER month_order AS prior_date
        FROM months m WINDOW month_order AS (PARTITION BY id ORDER BY observed_on DESC)
      )
      SELECT DISTINCT ON(id) id,department,observed_on,name,category,presentation,
        price,document_id,source_locator,brand,registration,product_line,
        ''::text AS municipality,'department'::text AS scope,
        CASE WHEN date_trunc('month',prior_date)=date_trunc('month',observed_on)-interval '1 month'
          THEN prior_price END AS previous_price,
        CASE WHEN date_trunc('month',prior_date)=date_trunc('month',observed_on)-interval '1 month'
          THEN prior_date END AS previous_date
      FROM history ORDER BY id,observed_on DESC,price`;
    return (await database().query(query, [department, id])).rows;
  }
  const locationKeys = grouped
    ? ""
    : `,department${municipal ? ",municipality" : ""}`;
  // A national all-history catalog touches thousands of identities. Discover
  // keys once, then keep each current/prior-price read below the SQL deadline;
  // the complete result and failures still share the existing catalog cache.
  const batchedHistory = historical && grouped && !department && !id;
  const identityQuery = batchedHistory ? `identities AS MATERIALIZED (
      SELECT id,CURRENT_DATE AS latest_date FROM unnest($3::text[]) AS selected(id) WHERE ($2='' OR id=$2)
    ` : `identities AS MATERIALIZED (
      SELECT id${locationKeys},max(observed_on) AS latest_date FROM ${table}
      WHERE ${period} AND ($1='' OR department=$1) AND ($2='' OR id=$2)
      GROUP BY id${locationKeys} ORDER BY id${locationKeys}
    `;
  const query = `WITH ${identityQuery}    ), winners AS MATERIALIZED (
      SELECT p.*${municipal ? "" : ",''::text AS municipality"} FROM identities i
      CROSS JOIN LATERAL (
        SELECT p.* FROM published_${table} p WHERE p.id=i.id AND p.observed_on<=i.latest_date
          AND ${period} AND ($1='' OR p.department=$1)
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
  if (batchedHistory) {
    const keys = (await database().query<{ id: string }>(`WITH RECURSIVE keys(id) AS (
      (SELECT id FROM ${table} ORDER BY id LIMIT 1)
      UNION ALL
      SELECT n.id FROM keys prior CROSS JOIN LATERAL (
        SELECT id FROM ${table} WHERE id>prior.id ORDER BY id LIMIT 1
      ) n
    ) SELECT id FROM keys ORDER BY id`)).rows.map((row) => row.id);
    const rows = [];
    for (let offset = 0; offset < keys.length; offset += 500) {
      rows.push(...(await database().query(query, [department, id, keys.slice(offset, offset + 500)])).rows);
    }
    return rows;
  }
  return (await database().query(query, [department, id])).rows;
}

/** Read original revision metadata once for the bounded result set. Direct legacy
 * detail URLs preserve their retained historical identity and remain accessible. */
async function loadInputs(department: string, scope = "department", historical = false, id = "", grouped = false) {
  const rows = await readInputRows(department, scope, historical, id, grouped);
  return id ? rows : reconcileInputCatalog(rows);
}

// Match the catalog endpoint's five-minute freshness contract and share work
// across concurrent screens. Individual input/location reads remain uncached.
const inputCatalogCache = new Map<
  string,
  { expires: number; result: ReturnType<typeof loadInputs> }
>();
export function inputs(
  department: string,
  scope = "department",
  historical = false,
  id = "",
  grouped = false,
) {
  if (!grouped) return loadInputs(department, scope, historical, id, grouped);
  const key = JSON.stringify([department, scope, historical, id, grouped]);
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
      `SELECT id,title,publisher,source_url,media_type,kind,reference_period,retrieved_at,page_count,octet_length(content) AS bytes,metadata FROM source_document WHERE id=$1 OR id=(SELECT document_id FROM document_alias WHERE alias=$1) LIMIT 1`,
      [id],
    )
  ).rows[0];
  if (!r) return null;
  const sourceReviews = (await db.query<{ observed_on: string | null }>(
    "SELECT DISTINCT observed_on::text FROM ingestion_asset WHERE document_id=$1 AND status='review' ORDER BY 1",
    [r.id],
  )).rows;
  if (sourceReviews.length) {
    const dates = sourceReviews.map((review) => review.observed_on).filter(Boolean);
    r.metadata.review_note = `La fuente tiene referencias pendientes de verificación${dates.length ? ": " + dates.join(", ") : ""}. Conservamos el archivo original; la fecha del enlace no sustituye la fecha validada de cada precio.`;
  }
  const reviewedRows = (await db.query<{ count: number }>(
    `SELECT count(DISTINCT r.source_locator)::int AS count
     FROM official_source_review r WHERE r.document_id=$1
     AND NOT EXISTS(SELECT 1 FROM official_price_quote q
       WHERE q.document_id=r.document_id AND q.source_locator=r.source_locator AND q.parsed_at>r.created_at)
     AND NOT EXISTS(SELECT 1 FROM historical_price h
       WHERE h.document_id=r.document_id AND h.source_locator=r.source_locator)`,
    [r.id],
  )).rows[0]?.count || 0;
  if (reviewedRows) {
    r.metadata.record_review_count = reviewedRows;
    r.metadata.record_review_note = `Hay ${reviewedRows.toLocaleString("es-CO")} ${reviewedRows === 1 ? "registro de este archivo pendiente" : "registros de este archivo pendientes"} de verificación. Se conservan en el historial y no se usan como precios publicados.`;
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
    let resolution = (await db.query<{
      resolution: {
        observation_date: string; printed_heading: string; corroborating_url: string;
        price_disagreements?: { product_name: string; market_name: string; workbook_price: number; companion_pdf_price: number }[];
      };
    }>(
      "SELECT details->'date_resolution' AS resolution FROM historical_price WHERE document_id=$1 AND details ? 'date_resolution' LIMIT 1",
      [r.id],
    )).rows[0]?.resolution;
    if (!resolution) {
      resolution = (await db.query<{ resolution: NonNullable<typeof resolution> }>(
        "SELECT record AS resolution FROM retained_record WHERE table_name='source_date_resolution' AND record->>'document_id'=$1 ORDER BY captured_at DESC LIMIT 1",
        [r.id],
      )).rows[0]?.resolution;
    }
    if (resolution) {
      r.metadata.date_resolution_note = `Fecha verificada: ${resolution.observation_date}. El encabezado original dice «${resolution.printed_heading}». Corroboramos la fecha con otra publicación oficial de DANE.`;
      r.metadata.date_evidence_url = resolution.corroborating_url;
      if (resolution.price_disagreements?.length) {
        r.metadata.price_disagreement_note = resolution.price_disagreements.map((item) =>
          `${item.product_name}, ${item.market_name}: el anexo publica $${item.workbook_price.toLocaleString("es-CO")} y el boletín $${item.companion_pdf_price.toLocaleString("es-CO")}. Conservamos el precio literal del anexo; las dos publicaciones difieren.`,
        ).join(" ");
      }
    }
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
  } else if (department && !input)
    r.records = (
      await db.query(
        "SELECT crop,activity,reference_year,percentages,source_row FROM crop_calendar WHERE department_id=$1 AND document_id=$2",
        [department.slice(0, 2), r.id],
      )
    ).rows;
  else if (input)
    r.records = (
      await db.query(
        `SELECT name,department,municipality,observed_on,presentation,price,source_locator,brand,registration FROM (SELECT *,''::text AS municipality FROM published_input_price UNION ALL SELECT * FROM published_input_municipal_price) i WHERE id=$1 AND document_id=$2 AND ($3='' OR department=$3) ORDER BY observed_on DESC LIMIT 100`,
        [input.slice(0, 500), r.id, department || ""],
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
    r.records = (
      await db.query(
        OFFICIAL_EVIDENCE_ROWS_SQL,
        [r.id, (filters.get("locator") || "").slice(0, 500)],
      )
    ).rows;
  }
  if (r.metadata?.ingestion_kind === "city-pdf") {
    r.records = (
      await db.query(
        "SELECT product_name,market_name,observed_on,presentation,quantity,source_unit,round_label,min_price,max_price,unit,min_unit_price,max_unit_price,source_page,source_locator FROM regional_price WHERE document_id=$1 ORDER BY source_page,source_locator",
        [r.id],
      )
    ).rows;
  }
  return r;
}
