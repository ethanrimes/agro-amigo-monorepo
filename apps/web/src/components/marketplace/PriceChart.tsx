"use client";
import { useId, useState } from "react";
import { dateLabel, money, type Point } from "@/lib/market-types";
export function PriceChart({
  points,
  label,
  unit = "COP / kg",
}: {
  points: Point[];
  label: string;
  unit?: string;
}) {
  const [months, setMonths] = useState(12);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId().replace(/:/g, "");
  const end = points.at(-1)?.date;
  const cutoff = end ? new Date(end + "T12:00:00Z") : new Date();
  cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
  const data = points.filter((p) => new Date(p.date + "T12:00:00Z") >= cutoff);
  const values = data.map((p) => p.price);
  const low = Math.min(...values) * 0.94;
  const high = Math.max(...values) * 1.04;
  const range = high - low || 1;
  const x = (i: number) => 65 + (i / Math.max(data.length - 1, 1)) * 715;
  const y = (v: number) => 205 - ((v - low) / range) * 170;
  const path = data
    .map((p, i) => `${i ? "L" : "M"} ${x(i)} ${y(p.price)}`)
    .join(" ");
  const selected = hover !== null ? data[hover] : null;
  return (
    <section className="chart-panel">
      <div className="chart-header">
        <div>
          <h2>{label}</h2>
          <p>
            {selected
              ? `${dateLabel(selected.date, true)} · ${money(selected.price)}`
              : unit}
          </p>
        </div>
        <div className="chart-tabs">
          {[3, 6, 12].map((m) => (
            <button
              key={m}
              className={months === m ? "active" : ""}
              aria-pressed={months === m}
              onClick={() => {
                setMonths(m);
                setHover(null);
              }}
            >
              {m} meses
            </button>
          ))}
        </div>
      </div>
      {data.length > 1 ? (
        <>
          <svg
            className="price-chart"
            viewBox="0 0 800 250"
            role="img"
            aria-label={`${label}. ${data.length} observaciones. Primera: ${money(data[0].price)}. Última: ${money(data.at(-1)!.price)}.`}
            onMouseLeave={() => setHover(null)}
          >
            <defs>
              <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#487655" stopOpacity=".18" />
                <stop offset="100%" stopColor="#487655" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[0, 0.5, 1].map((t) => (
              <g key={t}>
                <line
                  x1="65"
                  x2="780"
                  y1={y(low + range * t)}
                  y2={y(low + range * t)}
                  stroke="#e6e9e2"
                  strokeDasharray="4 5"
                />
                <text
                  x="0"
                  y={y(low + range * t) + 4}
                  fill="#737c71"
                  fontSize="11"
                >
                  {money(low + range * t)}
                </text>
              </g>
            ))}
            <path
              d={`${path} L ${x(data.length - 1)} 205 L 65 205 Z`}
              fill={`url(#${id})`}
            />
            <path
              d={path}
              fill="none"
              stroke="#3c6748"
              strokeWidth="2.7"
              strokeLinejoin="round"
            />
            {data.map((p, i) => (
              <circle
                key={p.date}
                cx={x(i)}
                cy={y(p.price)}
                r={selected === p ? 5 : 12}
                fill={selected === p ? "#3c6748" : "transparent"}
                onMouseEnter={() => setHover(i)}
              >
                <title>
                  {dateLabel(p.date)}: {money(p.price)}
                </title>
              </circle>
            ))}
            <text x="65" y="237" fill="#737c71" fontSize="12">
              {dateLabel(data[0].date, true)}
            </text>
            <text x="780" y="237" textAnchor="end" fill="#737c71" fontSize="12">
              {dateLabel(data.at(-1)!.date, true)}
            </text>
          </svg>
          <details className="chart-data">
            <summary>Ver datos en tabla</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>{unit}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((p) => (
                    <tr key={p.date}>
                      <td>{dateLabel(p.date)}</td>
                      <td>{money(p.price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p className="muted">
          Aún no hay suficientes observaciones para mostrar la evolución.
        </p>
      )}
    </section>
  );
}
