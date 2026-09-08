"use client";
import { useState } from "react";
import {
  IoRainyOutline,
  IoThermometerOutline,
  IoWarningOutline,
  IoLayersOutline,
  IoLocationOutline,
} from "react-icons/io5";
import { LocationMap } from "./LocationMap";
import { useData } from "@/components/marketplace/useData";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { ErrorState } from "@/components/marketplace/Shared";
import { number, dateLabel } from "@/lib/market-types";
import {
  FULL_MONTHS,
  inColombia,
  type LocationPoint,
  type LayerKey,
  type SpatialLayer,
  type SpatialReading,
  type ForecastGrid,
} from "@/lib/location-types";
import type { Weather } from "@/lib/planning-types";
const CATEGORIES: {
  id: LayerKey;
  label: string;
  icon: typeof IoRainyOutline;
}[] = [
  { id: "rain", label: "Lluvia", icon: IoRainyOutline },
  { id: "temperature", label: "Temperatura", icon: IoThermometerOutline },
  { id: "risk", label: "Tiempo severo", icon: IoWarningOutline },
  { id: "soil", label: "Suelos", icon: IoLayersOutline },
  { id: "erosion", label: "Erosión", icon: IoLayersOutline },
  { id: "flood", label: "Inundación", icon: IoWarningOutline },
];
const names: Record<string, string> = {
  rangos: "Lluvia habitual",
  rango: "Temperatura habitual",
  UCSuelo: "Unidad de suelo",
  PAISAJE: "Paisaje",
  TIPO_RELIE: "Relieve",
  TEXTURA: "Textura",
  PROFUNDIDA: "Profundidad",
  FERTILIDAD: "Fertilidad",
  ACIDEZ: "Acidez",
  DRENAJE: "Drenaje",
  PENDIENT_1: "Código de pendiente (IGAC)",
  CLIMA_1: "Clima ambiental",
  tipo: "Tipo de erosión",
  clas: "Forma de erosión",
  gra: "Grado de erosión",
  susceptible: "Susceptibilidad",
};
function PinReading({
  point,
  layer,
  month,
  title,
}: {
  point: LocationPoint;
  layer: SpatialLayer;
  month: number;
  title: string;
}) {
  const q = useData<SpatialReading>(
    `/api/location/point?layer=${layer.id}&month=${month}&lat=${point.latitude.toFixed(6)}&lon=${point.longitude.toFixed(6)}`,
  );
  return (
    <section className="zone-reading panel">
      <span className="eyebrow">{title}</span>
      <h3>{layer.title}</h3>
      <p className="muted">
        {point.latitude.toFixed(5)}, {point.longitude.toFixed(5)} ·{" "}
        {layer.monthly ? FULL_MONTHS[month - 1] + " · " : ""}
        {layer.unit}
      </p>
      {q.loading ? (
        <p role="status">Consultando la unidad cartográfica…</p>
      ) : q.error ? (
        <ErrorState message={q.error} retry={q.retry} />
      ) : (
        q.data && (
          <>
            {!q.data.records.length ? (
              <p className="inline-note">
                Sin unidad cartográfica reportada en este punto. Esto no permite
                concluir que el terreno sea apto o esté libre de amenaza.
              </p>
            ) : (
              q.data.records.map((row, i) => (
                <div key={i}>
                  {q.data!.records.length > 1 && (
                    <strong>
                      Unidad {i + 1} de {q.data!.records.length} en el punto
                    </strong>
                  )}
                  <dl className="zone-value-grid">
                    {layer.valueFields.map((f) => (
                      <div key={f}>
                        <dt>{names[f] || f}</dt>
                        <dd>
                          {row[f] === null
                            ? "Sin dato"
                            : String(row[f] ?? "Sin dato")}
                          {f === "rango" ? " °C" : ""}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))
            )}
            <EvidenceLink id={q.data.documentId}>
              Ver valores originales y consulta exacta
            </EvidenceLink>
          </>
        )
      )}
      <p className="field-help">{layer.note}</p>
    </section>
  );
}
function PointForecast({
  point,
  title,
}: {
  point: LocationPoint;
  title: string;
}) {
  const w = useData<Weather>(
    `/api/planning/weather?lat=${point.latitude}&lon=${point.longitude}`,
  );
  const d = w.data?.payload.daily;
  return (
    <section className="zone-reading panel">
      <span className="eyebrow">{title}</span>
      <h3>Los próximos días en este punto</h3>
      {w.loading ? (
        <p role="status">Consultando el pronóstico…</p>
      ) : w.error ? (
        <ErrorState message={w.error} retry={w.retry} />
      ) : (
        w.data &&
        d && (
          <>
            {w.data.stale && (
              <p role="alert" className="inline-warning">
                Pronóstico guardado sin actualizar. Revisa sus fechas antes de
                usarlo.
              </p>
            )}
            <div className="forecast-day-strip">
              {d.time.map((date, i) => (
                <div key={date}>
                  <b>{dateLabel(date, true)}</b>
                  <span>
                    🌧{" "}
                    {d.precipitation_sum[i] === null
                      ? "—"
                      : number(d.precipitation_sum[i]!)}{" "}
                    mm
                  </span>
                  <span>
                    {d.temperature_2m_min[i] ?? "—"}–
                    {d.temperature_2m_max[i] ?? "—"} °C
                  </span>
                  <small>Viento {d.wind_speed_10m_max[i] ?? "—"} km/h</small>
                </div>
              ))}
            </div>
            <EvidenceLink id={w.data.id}>
              Ver pronóstico conservado y unidades
            </EvidenceLink>
            <p className="field-help">
              Open-Meteo · consultado{" "}
              {new Date(w.data.fetched_at).toLocaleString("es-CO", {
                timeZone: "America/Bogota",
              })}
              . Punto del modelo: {w.data.payload.latitude},{" "}
              {w.data.payload.longitude}; puede diferir del pin.
            </p>
          </>
        )
      )}
    </section>
  );
}
export function ZoneExplorer({
  pin,
  focus,
  onPin,
}: {
  pin: LocationPoint | null;
  focus: LocationPoint | null;
  onPin: (p: LocationPoint) => void;
}) {
  const layers = useData<SpatialLayer[]>("/api/location/layers");
  const [category, setCategory] = useState<LayerKey>("rain"),
    [horizon, setHorizon] = useState("month"),
    [month, setMonth] = useState(
      Number(
        new Intl.DateTimeFormat("en", {
          timeZone: "America/Bogota",
          month: "numeric",
        }).format(new Date()),
      ),
    ),
    [day, setDay] = useState<number | null>(null),
    [inspection, setInspection] = useState<LocationPoint | null>(null),
    [opacity, setOpacity] = useState(0.65),
    [viewport, setViewport] = useState<{
      point: LocationPoint;
      step: number;
    } | null>(null);
  const climate = category === "rain" || category === "temperature",
    forecastMode = category === "risk" || (climate && horizon === "forecast");
  const selected = forecastMode
    ? null
    : layers.data?.find(
        (l) =>
          l.id ===
          (climate
            ? category + "-" + (horizon === "year" ? "year" : "month")
            : category),
      ) || null;
  const grid = useData<ForecastGrid>(
    forecastMode && viewport && inColombia(viewport.point)
      ? `/api/location/grid?lat=${(Math.round(viewport.point.latitude / viewport.step) * viewport.step).toFixed(3)}&lon=${(Math.round(viewport.point.longitude / viewport.step) * viewport.step).toFixed(3)}&step=${viewport.step}`
      : null,
  );
  const point = inspection || pin;
  const staticLegend = selected?.legend || [];
  return (
    <div className="zone-explorer">
      <div className="zone-intro">
        <div>
          <span className="eyebrow">CONOCE EL TERRENO</span>
          <h2>Una ubicación. Muchas respuestas.</h2>
          <p>
            Explora las capas, cambia el período y consulta cualquier punto del
            mapa.
          </p>
        </div>
        <span className="zone-source-mark">IDEAM · IGAC · Open-Meteo</span>
      </div>
      <div className="zone-layer-tabs" role="group" aria-label="Capas del mapa">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            aria-pressed={category === c.id}
            onClick={() => setCategory(c.id)}
          >
            <c.icon />
            <span>{c.label}</span>
          </button>
        ))}
      </div>
      <div className="zone-controls">
        {climate && (
          <label>
            Horizonte de la información
            <select
              aria-label="Horizonte de la información"
              value={horizon}
              onChange={(e) => setHorizon(e.target.value)}
            >
              <option value="forecast">Pronóstico · próximos 7 días</option>
              <option value="month">Clima habitual · por mes</option>
              <option value="year">Clima habitual · año completo</option>
            </select>
          </label>
        )}
        {climate && horizon === "month" && (
          <label>
            Mes habitual
            <select
              aria-label="Mes habitual"
              value={month}
              onChange={(e) => setMonth(+e.target.value)}
            >
              {FULL_MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        )}
        {forecastMode && (
          <label>
            Días del pronóstico
            <select
              value={day === null ? "all" : day}
              onChange={(e) =>
                setDay(e.target.value === "all" ? null : +e.target.value)
              }
            >
              <option value="all">Los próximos 7 días</option>
              {grid.data?.samples[0]?.dates.map((d, i) => (
                <option key={d} value={i}>
                  {dateLabel(d, true)}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="zone-opacity">
          Visibilidad de la capa{" "}
          <input
            aria-label="Visibilidad de la capa"
            type="range"
            min="0.15"
            max="1"
            step="0.05"
            value={opacity}
            onChange={(e) => setOpacity(+e.target.value)}
          />
        </label>
      </div>
      {layers.error && (
        <ErrorState message={layers.error} retry={layers.retry} />
      )}
      <LocationMap
        pin={pin}
        focus={focus}
        inspection={inspection}
        layer={selected}
        month={month}
        forecast={forecastMode ? grid.data : null}
        category={category}
        day={day}
        opacity={opacity}
        onInspect={(p) => {
          if (inColombia(p)) setInspection(p);
        }}
        onViewport={(p, step) => setViewport({ point: p, step })}
      />
      <div className="zone-map-caption">
        <strong>
          {forecastMode
            ? category === "rain"
              ? "Lluvia acumulada del pronóstico (mm)"
              : category === "temperature"
                ? "Máxima del período pronosticado (°C)"
                : "Indicadores orientativos de atención"
            : selected?.title || "Cargando capa…"}
        </strong>
        <span>
          {forecastMode ? "Puntos del modelo meteorológico" : selected?.period}
        </span>
      </div>
      <div className="zone-legend" aria-label="Leyenda de la capa">
        {forecastMode ? (
          category === "risk" ? (
            <>
              <span>
                <i style={{ background: "#da912c" }} />
                Revisar condiciones
              </span>
              <span>
                <i style={{ background: "#6b8d86" }} />
                Sin umbral activado
              </span>
            </>
          ) : category === "rain" ? (
            ["0–10", "10–30", "30–80", "80–150", "≥150"].map((v, i) => (
              <span key={v}>
                <i
                  style={{
                    background: [
                      "#e1e8bc",
                      "#a5d5dc",
                      "#4f9bb9",
                      "#176696",
                      "#40337d",
                    ][i],
                  }}
                />
                {v} mm
              </span>
            ))
          ) : (
            ["<15", "15–24", "24–30", "30–35", "≥35"].map((v, i) => (
              <span key={v}>
                <i
                  style={{
                    background: [
                      "#5798ba",
                      "#8fbdb5",
                      "#e4c761",
                      "#dc824e",
                      "#a53d3d",
                    ][i],
                  }}
                />
                {v} °C
              </span>
            ))
          )
        ) : (
          staticLegend.map((l, i) => (
            <span key={i}>
              <i style={{ background: l.color }} />
              {l.label}
            </span>
          ))
        )}
      </div>
      {forecastMode ? (
        <div className="zone-provenance">
          {grid.loading && (
            <p role="status">Consultando puntos del pronóstico regional…</p>
          )}
          {grid.error && <ErrorState message={grid.error} retry={grid.retry} />}
          <p>
            Los círculos muestran consultas separadas del modelo; el espacio
            entre ellos no es una medición continua.{" "}
            {grid.data && (
              <>
                Separación de muestreo: {number(grid.data.step)}° (aprox.{" "}
                {number(grid.data.step * 111)} km norte-sur).{" "}
              </>
            )}
            Acerca el mapa para explorar más puntos.
          </p>
          {category === "risk" && (
            <p>
              Atención si algún día tiene lluvia ≥20 mm, viento ≥40 km/h, máxima
              ≥35 °C o mínima ≤2 °C. Son reglas orientativas de AgroAmigo, no
              alertas oficiales ni probabilidades de daño. No activar un umbral
              tampoco garantiza condiciones seguras.
            </p>
          )}
          {grid.data && (
            <EvidenceLink id={grid.data.documentId}>
              Fuente, fechas, puntos y reglas de cálculo
            </EvidenceLink>
          )}
          <a
            href="https://www.ideam.gov.co/sala-de-prensa/boletines"
            target="_blank"
            rel="noreferrer"
          >
            Consultar boletines y alertas oficiales del IDEAM ↗
          </a>
        </div>
      ) : (
        selected && (
          <div className="zone-provenance">
            <p>{selected.note}</p>
            <EvidenceLink id={selected.documentId}>
              Fuente de la capa, leyenda y escala
            </EvidenceLink>
          </div>
        )
      )}
      {inspection && (
        <div className="zone-inspection-bar">
          <span>
            <IoLocationOutline />
            Explorando {inspection.latitude.toFixed(5)},{" "}
            {inspection.longitude.toFixed(5)}
          </span>
          <button className="button primary" onClick={() => onPin(inspection)}>
            Fijar mi pin aquí
          </button>
          <button
            className="button secondary"
            onClick={() => setInspection(null)}
          >
            Cerrar consulta
          </button>
        </div>
      )}
      {!pin && (
        <p className="inline-note">
          Toca el mapa y elige «Fijar mi pin aquí», o usa el GPS. Puedes
          explorar sin registrar una finca.
        </p>
      )}
      <div className="zone-readings">
        {pin &&
          (selected ? (
            <PinReading
              key={`pin-${selected.id}-${month}-${pin.latitude}-${pin.longitude}`}
              point={pin}
              layer={selected}
              month={month}
              title="EN EL PIN DE MI FINCA"
            />
          ) : forecastMode ? (
            <PointForecast point={pin} title="EN EL PIN DE MI FINCA" />
          ) : null)}
        {inspection &&
          (selected ? (
            <PinReading
              key={`explore-${selected.id}-${month}-${inspection.latitude}-${inspection.longitude}`}
              point={inspection}
              layer={selected}
              month={month}
              title="EN EL PUNTO EXPLORADO"
            />
          ) : forecastMode ? (
            <PointForecast point={inspection} title="EN EL PUNTO EXPLORADO" />
          ) : null)}
      </div>
      {point && selected && (
        <details className="zone-extra-weather">
          <summary>
            Ver también el pronóstico de los próximos días en{" "}
            {inspection ? "el punto explorado" : "mi pin"}
          </summary>
          <PointForecast point={point} title="PRONÓSTICO A CORTO PLAZO" />
        </details>
      )}
    </div>
  );
}
