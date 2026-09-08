import type { Weather } from "./planning-types";

export const CURRENT_WEATHER_KEYS = [
  "temperature_2m", "apparent_temperature", "relative_humidity_2m",
  "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m", "is_day",
] as const;
export const HOURLY_WEATHER_KEYS = [
  "temperature_2m", "precipitation_probability", "precipitation",
  "weather_code", "wind_speed_10m",
] as const;
export const WEATHER_REFRESH_MS = 15 * 60_000;

// Open-Meteo returns local ISO strings without offsets for America/Bogota.
export function weatherTime(time: string) {
  return new Date(time + (/(Z|[+-]\d{2}:\d{2})$/.test(time) ? "" : "-05:00"));
}

export function hasCurrentWeather(payload: Weather["payload"]) {
  const c = payload.current, h = payload.hourly;
  return !!c && !!h && payload.timezone === "America/Bogota" &&
    Number.isFinite(weatherTime(c.time).getTime()) &&
    Number.isFinite(c.interval) && c.interval > 0 &&
    CURRENT_WEATHER_KEYS.every(k => c[k] === null ||
      (typeof c[k] === "number" && Number.isFinite(c[k]))) &&
    Array.isArray(h.time) && h.time.length >= 24 &&
    h.time.every((t, i) => typeof t === "string" && Number.isFinite(weatherTime(t).getTime()) &&
      (i === 0 || weatherTime(t) > weatherTime(h.time[i - 1]))) &&
    HOURLY_WEATHER_KEYS.every(k => Array.isArray(h[k]) && h[k].length === h.time.length &&
      h[k].every(v => v === null || (typeof v === "number" && Number.isFinite(v)))) &&
    payload.current_units?.temperature_2m === "°C" &&
    payload.current_units?.precipitation === "mm" &&
    payload.current_units?.wind_speed_10m === "km/h" &&
    payload.current_units?.relative_humidity_2m === "%" &&
    payload.hourly_units?.precipitation_probability === "%" &&
    payload.hourly_units?.temperature_2m === "°C" &&
    payload.hourly_units?.wind_speed_10m === "km/h" &&
    payload.hourly_units?.precipitation === "mm";
}

export function weatherDescription(code: number | null | undefined) {
  if (code == null) return "Estado no disponible";
  if (code === 0) return "Despejado";
  if (code === 1) return "Mayormente despejado";
  if (code === 2) return "Parcialmente nublado";
  if (code === 3) return "Nublado";
  if ([45, 48].includes(code)) return "Niebla";
  if ([51, 53, 55, 56, 57].includes(code)) return "Llovizna";
  if ([61, 63, 65, 66, 67].includes(code)) return "Lluvia";
  if ([71, 73, 75, 77, 85, 86].includes(code)) return "Nieve";
  if ([80, 81, 82].includes(code)) return "Chubascos";
  if ([95, 96, 99].includes(code)) return "Tormenta";
  return "Estado no disponible";
}

export function currentWeatherIsOld(weather: Weather, now = Date.now()) {
  const time = weather.payload.current?.time;
  return weather.stale || !time ||
    now - new Date(weather.fetched_at).getTime() >= 30 * 60_000 ||
    now - weatherTime(time).getTime() > 60 * 60_000;
}
