"use client";
import { MONTHS, percentile } from "@/lib/planning-math";
import { money, number, dateLabel } from "@/lib/market-types";
import type { Seasonality } from "@/lib/planning-types";
import { EvidenceLink } from "./EvidenceLink";
export function SeasonalChart({
  data,
  month,
  onMonth,
}: {
  data: Seasonality;
  month: number;
  onMonth: (m: number) => void;
}) {
  const valid = data.years.filter(
    (y) =>
      y.monthly_prices.length === 12 && y.monthly_prices.every((v) => v > 0),
  );
  if (valid.length < 3)
    return (
      <div className="inline-note">
        No hay al menos 3 años completos y comparables en este mercado. Puedes
        ingresar tus propios precios para simular una venta.
      </div>
    );
  const indices = MONTHS.map((_, m) =>
    percentile(
      valid.map(
        (y) =>
          (y.monthly_prices[m] /
            (y.monthly_prices.reduce((a, b) => a + b, 0) / 12)) *
          100,
      ),
      0.5,
    )!,
  );
  const max = Math.max(...indices, 110);
  return (
    <section className="panel seasonal-panel">
      <span className="eyebrow">LA HISTORIA AYUDA A PLANEAR</span>
      <h3>¿En qué meses ha variado el precio?</h3>
      <p>
        {data.latest?.market} · {valid.map((y) => y.reference_year).join(", ")}
      </p>
      <div
        className="seasonal-bars"
        role="group"
        aria-label="Patrón estacional por mes"
      >
        {indices.map((value, i) => (
          <button
            key={i}
            className={month === i + 1 ? "selected" : ""}
            aria-pressed={month === i + 1}
            onClick={() => onMonth(i + 1)}
            title={`${MONTHS[i]}: ${number(value)} respecto al promedio anual 100`}
          >
            <span className="bar-value">{Math.round(value)}</span>
            <span className="bar-track">
              <span style={{ height: (value / max) * 100 + "%" }} />
            </span>
            <span>{MONTHS[i]}</span>
          </button>
        ))}
      </div>
      <p className="privacy-note">
        100 = precio promedio de cada año. El gráfico muestra la mediana de los
        índices anuales del mismo producto y mercado; reduce el efecto del
        cambio general de precios entre años. No predice el mejor mes para
        vender.
      </p>
      <details className="source-explanation">
        <summary>Ver precios históricos y método</summary>
        <p>{data.method}</p>
        <div className="table-scroll">
          <table className="data-table">
            <caption>
              Precios mensuales nominales en COP/{data.unit}. Sin ajuste por
              inflación.
            </caption>
            <thead>
              <tr>
                <th>Año</th>
                {MONTHS.map((m) => (
                  <th key={m}>{m}</th>
                ))}
                <th>Fuente</th>
              </tr>
            </thead>
            <tbody>
              {valid.map((y) => (
                <tr key={y.reference_year}>
                  <th>{y.reference_year}</th>
                  {y.monthly_prices.map((p, i) => (
                    <td key={i} title={y.source_rows[i]}>
                      {money(p)}
                    </td>
                  ))}
                  <td>
                    <EvidenceLink id={y.document_id}>Original</EvidenceLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.latest && (
          <p>
            Precio base: {money(data.latest.price)} por {data.unit}, del{" "}
            {dateLabel(data.latest.date)}.
          </p>
        )}
        <EvidenceLink id="planning-method">Todas las fórmulas</EvidenceLink>
      </details>
    </section>
  );
}
