export type LocationPoint = { latitude: number; longitude: number };
export type LayerKey =
  | "rain"
  | "temperature"
  | "risk"
  | "soil"
  | "erosion"
  | "flood";
export type SpatialLayer = {
  id: string;
  category: LayerKey;
  title: string;
  publisher: string;
  service: string;
  layer: number;
  period: string;
  unit: string;
  note: string;
  monthly: boolean;
  monthField?: string;
  monthYear?: number;
  valueFields: string[];
  documentId: string;
  legend: { label: string; color: string }[];
};
export type SpatialReading = {
  documentId: string;
  fetchedAt: string;
  records: Record<string, unknown>[];
  sourceUrl: string;
};
export type ForecastSample = LocationPoint & {
  modelLatitude: number;
  modelLongitude: number;
  dates: string[];
  rain: (number | null)[];
  low: (number | null)[];
  high: (number | null)[];
  wind: (number | null)[];
};
export type ForecastGrid = {
  documentId: string;
  fetchedAt: string;
  samples: ForecastSample[];
  step: number;
  stale: boolean;
};
export const FULL_MONTHS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];
export function inColombia(p: LocationPoint) {
  return (
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    p.latitude >= -5 &&
    p.latitude <= 14 &&
    p.longitude >= -82 &&
    p.longitude <= -66
  );
}
export function forecastValue(
  p: ForecastSample,
  category: LayerKey,
  day: number | null,
) {
  const indices = day === null ? p.dates.map((_, i) => i) : [day];
  const valid = (a: (number | null)[]) =>
    indices.every((i) => typeof a[i] === "number" && Number.isFinite(a[i]));
  if (category === "rain")
    return valid(p.rain) ? indices.reduce((s, i) => s + p.rain[i]!, 0) : null;
  if (category === "temperature")
    return valid(p.high) ? Math.max(...indices.map((i) => p.high[i]!)) : null;
  if (![p.rain, p.high, p.low, p.wind].every(valid)) return null;
  return indices.some(
    (i) =>
      p.rain[i]! >= 20 ||
      p.wind[i]! >= 40 ||
      p.high[i]! >= 35 ||
      p.low[i]! <= 2,
  )
    ? 1
    : 0;
}
