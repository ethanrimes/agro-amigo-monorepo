import type {
  Offer,
  Seasonality,
  Weather,
  FarmProfile,
} from "./planning-types";
export const MONTHS = [
  "Ene",
  "Feb",
  "Mar",
  "Abr",
  "May",
  "Jun",
  "Jul",
  "Ago",
  "Sep",
  "Oct",
  "Nov",
  "Dic",
];
export function fold(s: string) {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}
export function bogotaToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function addDays(iso: string, days: number) {
  const d = new Date(iso + "T12:00:00Z");
  if (!Number.isFinite(d.getTime()) || !Number.isFinite(days)) return null;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
export function percentile(values: number[], q: number) {
  const a = [...values].filter(Number.isFinite).sort((a, b) => a - b);
  if (!a.length) return null;
  const at = (a.length - 1) * q,
    lo = Math.floor(at),
    hi = Math.ceil(at);
  return a[lo] + (a[hi] - a[lo]) * (at - lo);
}
export function seasonalPrices(data: Seasonality, targetMonth: number) {
  if (!data.latest || targetMonth < 1 || targetMonth > 12) return null;
  const from = Number(data.latest.date.slice(5, 7)) - 1;
  const ratios = data.years
    .filter(
      (y) =>
        y.monthly_prices.length === 12 &&
        y.monthly_prices.every((p) => Number.isFinite(p) && p > 0),
    )
    .map((y) => y.monthly_prices[targetMonth - 1] / y.monthly_prices[from]);
  if (ratios.length < 3) return null;
  return {
    low: data.latest.price * percentile(ratios, 0.25)!,
    typical: data.latest.price * percentile(ratios, 0.5)!,
    high: data.latest.price * percentile(ratios, 0.75)!,
    samples: ratios.length,
  };
}
export function offerResult(
  offer: Offer,
  availableKg: number,
  today = bogotaToday(),
) {
  const fields = [
    offer.price,
    offer.acceptedKg,
    offer.deductionPercent,
    offer.transport,
    offer.packaging,
    offer.fees,
    offer.paymentDays,
  ];
  if (
    fields.some((v) => v.trim() === "" || !Number.isFinite(+v)) ||
    +offer.price <= 0 ||
    +offer.acceptedKg <= 0 ||
    +offer.acceptedKg > availableKg ||
    +offer.deductionPercent < 0 ||
    +offer.deductionPercent > 100 ||
    +offer.transport < 0 ||
    +offer.packaging < 0 ||
    +offer.fees < 0 ||
    +offer.paymentDays < 0 ||
    !Number.isInteger(+offer.paymentDays) ||
    +offer.paymentDays > 365
  )
    return null;
  const gross = +offer.price * +offer.acceptedKg,
    deduction = (gross * +offer.deductionPercent) / 100;
  const costs = +offer.transport + +offer.packaging + +offer.fees;
  return {
    gross,
    deduction,
    costs,
    net: gross - deduction - costs,
    netKg: (gross - deduction - costs) / +offer.acceptedKg,
    remainingKg: availableKg - +offer.acceptedKg,
    expired: !!offer.expires && offer.expires < today,
    paymentDays: +offer.paymentDays,
  };
}
export type WorkSignal = {
  id: string;
  level: "attention" | "opportunity" | "info";
  title: string;
  action: string;
  reason: string;
  date: string;
};
export function weatherSignals(
  weather: Weather,
  profile: FarmProfile,
  crop: string,
): WorkSignal[] {
  const d = weather.payload.daily,
    signals: WorkSignal[] = [];
  if (weather.stale)
    return [
      {
        id: "weather-stale",
        level: "attention",
        title: "Actualiza el pronóstico antes de trabajar",
        action:
          "No fue posible actualizar la última consulta. Confirma las condiciones actuales.",
        reason:
          "Pronóstico guardado; no se generan ventanas de trabajo con datos vencidos.",
        date: d.time[0],
      },
    ];
  const rain = d.precipitation_sum.findIndex((v) => v !== null && v >= 20);
  if (rain >= 0)
    signals.push({
      id: "rain-" + d.time[rain],
      level: "attention",
      title:
        profile.stage === "harvest"
          ? "Prepara la cosecha para la lluvia"
          : "Revisa desagües y puntos de encharcamiento",
      action:
        profile.stage === "harvest"
          ? "Revisa el resguardo del producto y confirma el acceso del transporte."
          : "Recorre los puntos que suelen acumular agua antes de la lluvia prevista.",
      reason: `${d.precipitation_sum[rain]} mm previstos en 24 horas. Regla de planificación: 20 mm o más; no es una alerta oficial.`,
      date: d.time[rain],
    });
  const dry = d.time.findIndex(
    (_, i) =>
      i < d.time.length - 1 &&
      [i, i + 1].every(
        (k) =>
          d.precipitation_sum[k] !== null &&
          d.precipitation_sum[k]! <= 1 &&
          d.precipitation_probability_max[k] !== null &&
          d.precipitation_probability_max[k]! < 30,
      ),
  );
  if (dry >= 0 && (profile.stage === "harvest" || fold(crop) === "cafe"))
    signals.push({
      id: "dry-" + d.time[dry],
      level: "opportunity",
      title: "Posible ventana con poca lluvia",
      action:
        "Prepara el área de secado y revisa el pronóstico horario antes de sacar el producto. Mantén una opción para cubrirlo.",
      reason: `Dos días con hasta 1 mm/día y probabilidad de lluvia menor a 30 %. No garantiza secado completo.`,
      date: d.time[dry],
    });
  const hot = d.temperature_2m_max.findIndex((v) => v !== null && v >= 32);
  if (hot >= 0)
    signals.push({
      id: "heat-" + d.time[hot],
      level: "attention",
      title: "Organiza las labores más pesadas temprano",
      action:
        "Considera las horas más frescas para el trabajo y revisa disponibilidad de agua.",
      reason: `Máxima prevista de ${d.temperature_2m_max[hot]} °C. Umbral de planificación: 32 °C.`,
      date: d.time[hot],
    });
  const sum = d.precipitation_sum.slice(0, 5);
  if (
    !profile.irrigation &&
    sum.length === 5 &&
    sum.every((v) => v !== null) &&
    sum.reduce<number>((a, b) => a + b!, 0) < 5
  )
    signals.push({
      id: "water-" + d.time[0],
      level: "attention",
      title:
        profile.stage === "planting"
          ? "Comprueba la humedad antes de sembrar"
          : "Revisa la humedad del suelo",
      action:
        profile.stage === "flowering"
          ? "Recorre el cultivo en floración y revisa señales de falta de agua."
          : "Comprueba la humedad en campo y la disponibilidad de agua antes de programar labores.",
      reason:
        "Menos de 5 mm previstos en 5 días y finca sin riego registrado. No calcula dosis de riego.",
      date: d.time[0],
    });
  if (!signals.length)
    signals.push({
      id: "review-" + d.time[0],
      level: "info",
      title: "Haz un recorrido de observación",
      action:
        "Revisa el cultivo y organiza materiales para las próximas labores. Consulta de nuevo el clima antes de salir.",
      reason:
        "No se activaron los umbrales de planificación. Esto no descarta problemas en la finca.",
      date: d.time[0],
    });
  return signals.slice(0, 4);
}
export function cropMapKeys(
  crop: string,
  variety = "",
  month = new Date().getMonth() + 1,
) {
  const c = fold(crop),
    v = fold(variety),
    s = month <= 6 ? "s1" : "s2";
  if (c === "banano") return v.includes("export") ? ["banano"] : [];
  if (c === "cafe") return ["cafe"];
  if (c === "aguacate") return v.includes("hass") ? ["aguacate_hass"] : [];
  if (c === "papa") return ["papa_" + s];
  if (c === "maiz") return v.includes("tradicional") ? [] : ["maiz_" + s];
  if (c === "cebolla de bulbo") return ["cebolla_bulbo_" + s];
  if (c === "arroz") return v.includes("secano") ? ["arroz_secano"] : [];
  return (
    (
      {
        platano: ["platano"],
        cacao: ["cacao"],
        frijol: ["frijol_comercial"],
        yuca: ["yuca"],
        banano: ["banano"],
        pimenton: ["pimenton"],
      } as Record<string, string[]>
    )[c] || []
  );
}
