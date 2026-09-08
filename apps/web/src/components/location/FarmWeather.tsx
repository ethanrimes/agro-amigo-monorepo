"use client";
import { useEffect, useState } from "react";
import { IoSunnyOutline, IoCloudyOutline, IoRainyOutline, IoThunderstormOutline, IoRefreshOutline, IoWaterOutline, IoNavigateOutline } from "react-icons/io5";
import type { Weather } from "@/lib/planning-types";
import type { LocationPoint } from "@/lib/location-types";
import { currentWeatherIsOld, weatherDescription, weatherTime, WEATHER_REFRESH_MS } from "@/lib/weather-data";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import styles from "./farm-weather.module.css";

const value = (v: number | null | undefined, unit = "") => v == null ? "Sin dato" :
  `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(v)}${unit}`;
const timeLabel = (time: string, full = false) => weatherTime(time).toLocaleString("es-CO", {
  timeZone: "America/Bogota", ...(full ? { day: "numeric", month: "short" } as const : {}),
  hour: "numeric", minute: "2-digit", hour12: true,
});
function ConditionIcon({ code }: { code: number | null | undefined }) {
  const Icon = code != null && code >= 95 ? IoThunderstormOutline :
    code != null && code >= 51 ? IoRainyOutline : code != null && code > 1 ? IoCloudyOutline : IoSunnyOutline;
  return <Icon aria-hidden="true" />;
}

export function FarmWeather({ point, name }: { point: LocationPoint; name: string }) {
  // Remount for a different pin: never show the previous finca's conditions.
  return <WeatherAtPin key={`${point.latitude},${point.longitude}`} point={point} name={name} />;
}
function WeatherAtPin({ point, name }: { point: LocationPoint; name: string }) {
  const [weather, setWeather] = useState<Weather | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [revision, setRevision] = useState(0), [view, setView] = useState<"hours" | "days">("hours");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const update = () => {
      setNow(Date.now());
      if (document.visibilityState === "visible" && navigator.onLine)
        setRevision(n => n + 1);
    };
    const timer = window.setInterval(update, WEATHER_REFRESH_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 60_000);
    document.addEventListener("visibilitychange", update);
    window.addEventListener("online", update);
    return () => {
      clearInterval(timer); clearInterval(clock);
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("online", update);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    fetch(`/api/planning/weather?lat=${point.latitude}&lon=${point.longitude}`, {
      signal: controller.signal, cache: "no-store",
    }).then(async r => {
      if (!r.ok) throw new Error("No pudimos actualizar el tiempo. Intenta de nuevo.");
      return r.json() as Promise<Weather>;
    }).then(data => { if (!controller.signal.aborted) { setWeather(data); setNow(Date.now()); } })
      .catch(e => { if (e.name !== "AbortError") setError("No pudimos actualizar el tiempo. Intenta de nuevo."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [point.latitude, point.longitude, revision]);

  const current = weather?.payload.current, hourly = weather?.payload.hourly, daily = weather?.payload.daily;
  const old = !!weather && (currentWeatherIsOld(weather, now) || !!error);
  const tooOld = !!weather && now - new Date(weather.fetched_at).getTime() >= 24 * 3600_000;
  const hourIndices = hourly?.time.map((t, i) => ({ t, i }))
    .filter(({ t }) => weatherTime(t).getTime() > now).slice(0, 24) || [];
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(now);
  const days = daily?.time.map((date, i) => ({ date, i })).filter(({ date }) => date >= today) || [];
  return <section className={styles.weather} aria-label="Tiempo y pronóstico de mi finca" aria-busy={loading}>
    <header className={styles.heading}>
      <div><span className={styles.kicker}>EL TIEMPO EN TU FINCA</span><h2>{name}</h2></div>
      <button className={styles.refresh} disabled={loading} onClick={() => setRevision(n => n + 1)} aria-label="Actualizar tiempo">
        <IoRefreshOutline aria-hidden="true" /> {loading ? "Consultando…" : "Actualizar"}
      </button>
    </header>
    {loading && !weather && <p role="status">Consultando el tiempo en tu pin…</p>}
    {error && <p role="alert" className={styles.warning}>{error}</p>}
    {weather && <>
      {old && <p role="status" className={styles.warning}>Datos sin actualizar. No representan necesariamente las condiciones actuales.</p>}
      {tooOld ? <p>La última consulta tiene más de un día. Actualiza para ver el tiempo y el pronóstico.</p> : <>
        {current ? <div className={styles.current}>
          <div className={styles.temperature}>
            <ConditionIcon code={current.weather_code} />
            <div><span>{old ? "Último dato disponible" : "Ahora · estimación del modelo"}</span>
              <strong>{value(current.temperature_2m, " °C")}</strong>
              <span>{weatherDescription(current.weather_code)}</span>
              <small>Sensación térmica {value(current.apparent_temperature, " °C")}</small>
            </div>
          </div>
          <dl className={styles.metrics}>
            <div><dt><IoWaterOutline /> Humedad</dt><dd>{value(current.relative_humidity_2m, " %")}</dd></div>
            <div><dt><IoRainyOutline /> Lluvia en {value(current.interval / 60)} min</dt><dd>{value(current.precipitation, " mm")}</dd></div>
            <div><dt><IoNavigateOutline /> Viento</dt><dd>{value(current.wind_speed_10m, " km/h")}</dd></div>
            <div><dt>Ráfagas</dt><dd>{value(current.wind_gusts_10m, " km/h")}</dd></div>
          </dl>
        </div> : <p>No hay condiciones actuales en esta consulta guardada. Puedes consultar su pronóstico.</p>}
        <div className={styles.switch} role="group" aria-label="Horizonte del pronóstico">
          <button aria-pressed={view === "hours"} onClick={() => setView("hours")}>Próximas 24 horas</button>
          <button aria-pressed={view === "days"} onClick={() => setView("days")}>Próximos 7 días</button>
        </div>
        {view === "hours" ? <>
          <p className={styles.explanation}>La probabilidad indica qué tan posible es que llueva; los milímetros, la cantidad estimada en cada hora.</p>
          {hourly && hourIndices.length ? <div className={styles.hours} tabIndex={0} role="region" aria-label="Pronóstico por hora; desplaza para ver más">
            {hourIndices.map(({ t, i }) => <article key={t} className={styles.hour}>
              <time dateTime={`${t}-05:00`}>{timeLabel(t)}<small>{weatherTime(t).toLocaleDateString("es-CO", { timeZone: "America/Bogota", weekday: "short", day: "numeric" })}</small></time>
              <ConditionIcon code={hourly.weather_code[i]} />
              <strong>{value(hourly.temperature_2m[i], " °C")}</strong>
              <span className={styles.condition}>{weatherDescription(hourly.weather_code[i])}</span>
              <span>Lluvia {value(hourly.precipitation_probability[i], " %")}</span>
              <span>{value(hourly.precipitation[i], " mm")}</span>
              <small>{value(hourly.wind_speed_10m[i], " km/h")}</small>
            </article>)}
          </div> : <p>No hay horas futuras disponibles en esta consulta. Actualiza el pronóstico.</p>}
        </> : <div className={styles.days}>
          {daily && days.length ? days.map(({ date, i }) => <article key={date} className={styles.day}>
            <div><strong>{date === today ? "Hoy" : new Date(`${date}T12:00:00-05:00`).toLocaleDateString("es-CO", { timeZone: "America/Bogota", weekday: "long" })}</strong><small>{date}</small></div>
            <div className={styles.dayCondition}><ConditionIcon code={daily.weather_code[i]} /><span>{weatherDescription(daily.weather_code[i])}</span></div>
            <div><strong>{value(daily.temperature_2m_max[i], "°")}</strong> / {value(daily.temperature_2m_min[i], "°")}<small>Máx. / mín. °C</small></div>
            <div><strong>{value(daily.precipitation_probability_max[i], " %")}</strong><small>{value(daily.precipitation_sum[i], " mm")} de lluvia</small></div>
            <div><span>{value(daily.wind_speed_10m_max[i], " km/h")}</span><small>Viento máximo</small></div>
          </article>) : <p>No hay días futuros disponibles. Actualiza el pronóstico.</p>}
        </div>}
      </>}
      <footer className={styles.source}>
        {current && <span>Hora del dato: {timeLabel(current.time, true)} · Colombia.</span>}
        <span>Última consulta: {new Date(weather.fetched_at).toLocaleString("es-CO", { timeZone: "America/Bogota" })}. Actualización cada 15 minutos mientras esta vista esté abierta.</span>
        <p>Open-Meteo · estimaciones meteorológicas, no mediciones de un sensor en la finca. La cuadrícula del modelo ({weather.payload.latitude}, {weather.payload.longitude}) puede diferir del pin. El pronóstico cambia y su incertidumbre aumenta con los días.</p>
        <div><EvidenceLink id={`weather-${weather.id}`}>Ver datos y unidades guardados en Azure</EvidenceLink>
          <a href={`/api/evidence/weather-${weather.id}/content`} download="tiempo-mi-finca.json">Descargar datos</a>
          <a href="https://open-meteo.com/en/docs" target="_blank" rel="noopener noreferrer">Fuente y metodología ↗</a></div>
      </footer>
    </>}
  </section>;
}
