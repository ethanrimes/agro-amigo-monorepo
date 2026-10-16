"use client";
import { useId, useState } from "react";
import { dateLabel, dateSearchAliases, money, type HistorySource, type Point } from "@/lib/market-types";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { SearchableSelect } from "@/components/ui/SearchableSelect";

type EvidenceContext = {
  product?: string;
  productName?: string;
  input?: string;
  department?: string;
  municipality?: string;
  presentation?: string;
  units?: string;
  currency?: string;
};
function MultiHistorySources({ sources, date, context, unit }: { sources: HistorySource[]; date: string; context?: EvidenceContext; unit: string }) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const ordered = [...sources].sort((a, b) =>
    a.market_name.localeCompare(b.market_name) ||
    a.document_id.localeCompare(b.document_id) ||
    (a.source_locator || "").localeCompare(b.source_locator || ""),
  );
  const sourceId = (source: HistorySource) => JSON.stringify([
    source.document_id, source.source_locator, source.source_page, source.market_id,
  ]);
  const selected = ordered.find((source) => sourceId(source) === selectedId);
  const sourceLink = (source: HistorySource, index: number) => (
    <EvidenceLink
      {...context}
      id={source.document_id}
      locator={source.source_locator || undefined}
      page={source.source_page || undefined}
      market={source.market_id}
      marketName={source.market_name}
      month={date}
      units={source.source_units || context?.units}
    >
      Fuente {index + 1} · {source.source_name ? `${source.source_name} · ` : ""}{source.market_name}
    </EvidenceLink>
  );
  return (
    <details
      className="history-row-source"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Consultar {sources.length} fuentes</summary>
      {open && (
        ordered.length <= 6 ? (
          <ul>
            {ordered.map((source, index) => (
              <li key={sourceId(source)}>{sourceLink(source, index)}</li>
            ))}
          </ul>
        ) : (
          <div>
            <SearchableSelect
              label="Consultar una fuente de la fecha"
              placeholder="Busca mercado, fecha o unidad…"
              value={selectedId}
              options={ordered.map((source) => ({
                id: sourceId(source),
                label: source.market_name,
                detail: `${dateLabel(date)} · ${source.source_units || context?.units || unit}${source.source_locator ? ` · ${source.source_locator}` : ""}`,
              }))}
              onChange={setSelectedId}
              emptyLabel="Busca y elige una fuente exacta"
            />
            {selected && <p className="history-row-source">{sourceLink(selected, ordered.indexOf(selected))}</p>}
          </div>
        )
      )}
    </details>
  );
}
function HistoryPointSources({ point, context, unit, label = "Consultar fuente" }: { point: Point; context?: EvidenceContext; unit: string; label?: string }) {
  if (!point.sources?.length) return null;
  if (point.sources.length > 1) {
    return <MultiHistorySources key={point.date} sources={point.sources} date={point.date} context={context} unit={unit} />;
  }
  const source = point.sources[0];
  return (
    <div className="history-row-source">
      <EvidenceLink
        {...context}
        id={source.document_id}
        locator={source.source_locator || undefined}
        page={source.source_page || undefined}
        market={source.market_id}
        marketName={source.market_name}
        month={point.date}
        units={source.source_units || context?.units}
      >
        {label}
      </EvidenceLink>
    </div>
  );
}
export function PriceChart({
  points,
  label,
  unit = "COP / kg",
  evidenceContext,
}: {
  points: Point[];
  label: string;
  unit?: string;
  allowAll?: boolean;
  evidenceContext?: EvidenceContext;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [tablePoint, setTablePoint] = useState("");
  const id = useId().replace(/:/g, "");
  const data = points;
  const pointKey = (point: Point) => point.observation_id || `${point.date}:${point.price}`;
  const values = data.map((p) => p.price);
  const low = Math.min(...values) * 0.94;
  const high = Math.max(...values) * 1.04;
  const range = high - low || 1;
  const x = (i: number) => data.length === 1 ? 422.5 : 65 + (i / Math.max(data.length - 1, 1)) * 715;
  const y = (v: number) => 205 - ((v - low) / range) * 170;
  const path = data
    .map((p, i) => `${i ? "L" : "M"} ${x(i)} ${y(p.price)}`)
    .join(" ");
  const selected = hover !== null ? data[hover] : null;
  const rankedDates = [...data].sort((a, b) => b.price - a.price || b.date.localeCompare(a.date));
  const selectedDate = rankedDates.find((p) => pointKey(p) === tablePoint);
  const tableDates = data.length > 24 ? rankedDates.slice(0, 12) : rankedDates;
  if (selectedDate && !tableDates.some((p) => pointKey(p) === tablePoint)) tableDates.push(selectedDate);
  return (
    <section className="chart-panel">
      <div className="chart-header">
        <div>
          <h2>{label}</h2>
          <p>
            {selected
              ? `${dateLabel(selected.date, true, true)} · ${money(selected.price)}`
              : unit}
          </p>
        </div>

      </div>
      {data.length ? (
        <>
          <svg
            className="price-chart"
            viewBox="0 0 800 250"
            role="img"
            aria-label={`${label}. ${data.length} observaciones. Primera: ${dateLabel(data[0].date)} · ${money(data[0].price)}. Última: ${dateLabel(data.at(-1)!.date)} · ${money(data.at(-1)!.price)}.`}
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
            {data.length > 1 && <path
              d={`${path} L ${x(data.length - 1)} 205 L 65 205 Z`}
              fill={`url(#${id})`}
            />}
            <path
              d={path}
              fill="none"
              stroke="#3c6748"
              strokeWidth="2.7"
              strokeLinejoin="round"
            />
            {data.map((p, i) => (
              <circle
                key={pointKey(p)}
                cx={x(i)}
                cy={y(p.price)}
                r={selected === p || data.length === 1 ? 5 : 12}
                fill={selected === p || data.length === 1 ? "#3c6748" : "transparent"}
                onMouseEnter={() => setHover(i)}
                onClick={() => setHover(i)}
              >
                <title>
                  {dateLabel(p.date)}: {money(p.price)}
                </title>
              </circle>
            ))}
            <text x={data.length === 1 ? 422.5 : 65} textAnchor={data.length === 1 ? "middle" : "start"} y="237" fill="#737c71" fontSize="12">
              {dateLabel(data[0].date, true, true)}
            </text>
            {data.length > 1 && <text x="780" y="237" textAnchor="end" fill="#737c71" fontSize="12">
              {dateLabel(data.at(-1)!.date, true, true)}
            </text>}
          </svg>
          {data.length === 1 && <p>Una observación · {dateLabel(data[0].date)} · {money(data[0].price)} · {unit}</p>}
          <details className="chart-data">
            <summary>Ver datos en tabla</summary>
            {data.length > 24 && (
              <>
                <p>La tabla muestra los doce precios mayores y la fecha elegida. Busca cualquier fecha del historial consultado.</p>
                <SearchableSelect
                  label="Consultar una fecha de esta tabla"
                  placeholder="Busca fecha, año o precio"
                  value={selectedDate ? tablePoint : ""}
                  options={rankedDates.map((p) => ({
                    id: pointKey(p), label: dateLabel(p.date),
                    detail: `${money(p.price)} · ${unit}`,
                    searchText: [dateSearchAliases(p.date), String(p.price)].join(" "),
                  }))}
                  onChange={setTablePoint}
                  selectionActions={selectedDate && (
                    <HistoryPointSources
                      point={selectedDate}
                      context={evidenceContext}
                      unit={unit}
                      label="Consultar fuente de la fecha seleccionada"
                    />
                  )}
                />
              </>
            )}
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>{unit}</th>
                  </tr>
                </thead>
                <tbody>
                  {tableDates.map((p) => (
                      <tr key={pointKey(p)}>
                        <td>{dateLabel(p.date)}</td>
                        <td>
                          {money(p.price)}
                          <HistoryPointSources point={p} context={evidenceContext} unit={unit} />
                        </td>
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
