"use client";
import { useEffect, useMemo, useState } from "react";
import {
  IoSunnyOutline,
  IoRainyOutline,
  IoCheckmarkCircleOutline,
  IoAlertCircleOutline,
} from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "./EvidenceLink";
import { weatherSignals, fold } from "@/lib/planning-math";
import { dateLabel, number } from "@/lib/market-types";
import type { FarmData, FarmProfile, Weather } from "@/lib/planning-types";
export function WeeklyPlan({
  farm,
  data,
}: {
  farm: FarmProfile;
  data: FarmData;
}) {
  const lat = farm.latitude ? +farm.latitude : data.municipality.latitude,
    lon = farm.longitude ? +farm.longitude : data.municipality.longitude;
  const forecast = useData<Weather>(
    `/api/planning/weather?lat=${lat}&lon=${lon}`,
  );
  const crop =
    data.crops.find((c) => c.crop_code === farm.cropCode)?.crop || "";
  const signals = useMemo(
    () => (forecast.data ? weatherSignals(forecast.data, farm, crop) : []),
    [forecast.data, farm, crop],
  );
  const [done, setDone] = useState<string[]>([]);
  useEffect(() => {
    try {
      setDone(
        JSON.parse(
          localStorage.getItem("agroamigo-tasks-" + farm.municipalityId) ||
            "[]",
        ).filter((s: unknown) => typeof s === "string"),
      );
    } catch {
      setDone([]);
    }
  }, [farm.municipalityId]);
  const toggle = (id: string) => {
    const next = done.includes(id)
      ? done.filter((x) => x !== id)
      : [...done, id].slice(-100);
    setDone(next);
    try {
      localStorage.setItem(
        "agroamigo-tasks-" + farm.municipalityId,
        JSON.stringify(next),
      );
    } catch {}
  };
  const advisories = data.advisories.filter(
    (a) => !a.crops.length || a.crops.some((c) => fold(c) === fold(crop)),
  );
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">UNA COSA A LA VEZ</span>
          <h2>Tu plan para esta semana</h2>
          <p>Revisa estas condiciones antes de organizar tus labores.</p>
        </div>
        <button className="button secondary" onClick={forecast.retry}>
          Actualizar clima
        </button>
      </div>
      {forecast.loading ? (
        <div className="panel" role="status">
          Consultando el pronóstico para {data.municipality.name}…
        </div>
      ) : forecast.error ? (
        <ErrorState message={forecast.error} retry={forecast.retry} />
      ) : (
        forecast.data && (
          <>
            <div className="work-signals">
              {signals.map((s) => (
                <article
                  className={
                    "work-signal " +
                    s.level +
                    (done.includes(s.id) ? " done" : "")
                  }
                  key={s.id}
                >
                  <span className="signal-icon">
                    {done.includes(s.id) ? (
                      <IoCheckmarkCircleOutline />
                    ) : s.level === "opportunity" ? (
                      <IoSunnyOutline />
                    ) : (
                      <IoAlertCircleOutline />
                    )}
                  </span>
                  <div>
                    <span className="signal-date">
                      {dateLabel(s.date, true)} ·{" "}
                      {s.level === "opportunity"
                        ? "Posible oportunidad"
                        : s.level === "attention"
                          ? "Para revisar"
                          : "Plan de trabajo"}
                    </span>
                    <h3>{s.title}</h3>
                    <p>{s.action}</p>
                    <details>
                      <summary>¿Por qué aparece?</summary>
                      <p>{s.reason}</p>
                      <EvidenceLink id={"weather-" + forecast.data!.id}>
                        Ver el pronóstico consultado
                      </EvidenceLink>
                      <EvidenceLink id="planning-method">
                        Ver cómo se genera esta sugerencia
                      </EvidenceLink>
                    </details>
                  </div>
                  <button
                    className="button secondary task-toggle"
                    aria-pressed={done.includes(s.id)}
                    onClick={() => toggle(s.id)}
                  >
                    {done.includes(s.id) ? "Revisado ✓" : "Ya lo revisé"}
                  </button>
                </article>
              ))}
            </div>
            <section className="panel weather-panel">
              <div className="section-heading">
                <div>
                  <h3>El clima de los próximos 7 días</h3>
                  <p>
                    {farm.latitude
                      ? "Punto indicado por ti"
                      : "Punto de referencia municipal"}{" "}
                    · {data.municipality.name}
                  </p>
                </div>
                <EvidenceLink id={"weather-" + forecast.data.id}>
                  Ver fuente
                </EvidenceLink>
              </div>
              {forecast.data.stale && (
                <p className="inline-warning">
                  Pronóstico guardado. No se pudo obtener una nueva consulta.
                </p>
              )}
              <div className="weather-days">
                {forecast.data.payload.daily.time.map((day, i) => {
                  const d = forecast.data!.payload.daily;
                  return (
                    <div className="weather-day" key={day}>
                      <strong>
                        {new Date(day + "T12:00:00Z").toLocaleDateString(
                          "es-CO",
                          {
                            weekday: "short",
                            day: "numeric",
                            timeZone: "America/Bogota",
                          },
                        )}
                      </strong>
                      {(d.precipitation_sum[i] || 0) > 1 ? (
                        <IoRainyOutline />
                      ) : (
                        <IoSunnyOutline />
                      )}
                      <span className="weather-temp">
                        {d.temperature_2m_max[i] === null
                          ? "—"
                          : Math.round(d.temperature_2m_max[i]!)}
                        °{" "}
                        <small>
                          {d.temperature_2m_min[i] === null
                            ? "—"
                            : Math.round(d.temperature_2m_min[i]!)}
                          °
                        </small>
                      </span>
                      <span>
                        {d.precipitation_sum[i] === null
                          ? "Sin dato"
                          : number(d.precipitation_sum[i]!) + " mm"}
                      </span>
                      <small>
                        {d.precipitation_probability_max[i] === null
                          ? ""
                          : d.precipitation_probability_max[i] + " % lluvia"}
                      </small>
                    </div>
                  );
                })}
              </div>
              <p className="privacy-note">
                Open-Meteo · Consultado{" "}
                {new Date(forecast.data.fetched_at).toLocaleString("es-CO", {
                  timeZone: "America/Bogota",
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                . Es un pronóstico de modelo y puede cambiar; las condiciones de
                tu lote pueden ser distintas.
              </p>
            </section>
          </>
        )
      )}
      {advisories.length > 0 && (
        <section className="advisories">
          <h2>Información para tener presente</h2>
          {advisories.map((a) => (
            <article className="panel advisory" key={a.id}>
              <span className="source-badge">
                {a.kind === "official_alert"
                  ? "Alerta oficial"
                  : a.kind === "monitoring"
                    ? "Vigilancia reportada"
                    : "Boletín de referencia"}{" "}
                · {dateLabel(a.published_on, true)}
              </span>
              <h3>{a.title}</h3>
              <p>{a.summary}</p>
              <p>
                <strong>Qué puedes hacer:</strong> {a.action}
              </p>
              <EvidenceLink
                id={a.document_id}
                page={a.source_page || undefined}
              >
                Consultar publicación y alcance
              </EvidenceLink>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
