"use client";
import { use, useState } from "react";
import { IoHeart, IoHeartOutline } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { dateLabel } from "@/lib/market-types";
import { CropPicture } from "@/components/marketplace/CropPicture";
import { usePreferences } from "@/components/marketplace/Preferences";
import { CatalogBackLink } from "@/components/marketplace/CatalogBackLink";
import {
  officialMoney,
  officialDetailLabels,
  type OfficialPrice,
} from "@/lib/official-types";
export default function Reference({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    [order, setOrder] = useState("price"),
    [history, setHistory] = useState("recent");
  const { saved, toggleSaved } = usePreferences();
  const savedKey = "reference:" + id;
  const { data, loading, error, retry } = useData<{
    reference: OfficialPrice;
    history: OfficialPrice[];
  }>("/api/references?id=" + id);
  if (loading) return <p role="status">Abriendo precios del producto…</p>;
  if (error) return <ErrorState message={error} retry={retry} />;
  if (!data) return null;
  const r = data.reference,
    cutoff = new Date(r.observed_on + "T12:00:00Z");
  cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
  const rows = data.history.filter(
      (x) =>
        history === "all" ||
        new Date(x.observed_on + "T12:00:00Z") >= cutoff,
    ),
    values = rows.map((x) => Number(x.price)),
    low = Math.min(...values) * 0.94,
    high = Math.max(...values) * 1.04,
    span = high - low || 1;
  const path = rows
    .map(
      (x, i) =>
        `${i ? "L" : "M"} ${10 + (i / Math.max(1, rows.length - 1)) * 700} ${180 - ((Number(x.price) - low) / span) * 160}`,
    )
    .join(" ");
  return (
    <>
      <CatalogBackLink />
      <div className="detail-intro">
        <div className="detail-picture">
          <CropPicture name={r.product_name} category={r.category} />
        </div>
        <div>
          <span className="eyebrow">{r.category}</span>
          <h1>{r.product_name}</h1>
          <p>{r.market}</p>
        </div>
        <button
          className="button secondary detail-save"
          aria-pressed={saved.includes(savedKey)}
          onClick={() => toggleSaved(savedKey)}
        >
          {saved.includes(savedKey) ? <IoHeart /> : <IoHeartOutline />}
          {saved.includes(savedKey) ? "Guardado" : "Guardar"}
        </button>
      </div>
      <section className="panel product-price-header">
        <div>
          <span>Último precio publicado</span>
          <strong
            className="current-product-price"
            data-testid="current-product-price"
            data-price={r.price}
            data-currency={r.currency}
            data-unit={r.unit}
          >
            {officialMoney(r.price, r.currency)}
          </strong>
          <p>
            Por {r.unit} · {dateLabel(r.observed_on)}
          </p>
          {typeof r.details.period_end === "string" && (
            <p>
              Período: {dateLabel(r.period_start || r.observed_on)} al{" "}
              {dateLabel(r.details.period_end)}
            </p>
          )}
          {r.min_price !== null && (
            <p>
              Rango: {officialMoney(r.min_price, r.currency)} –{" "}
              {officialMoney(r.max_price!, r.currency)} · Punto medio calculado
            </p>
          )}
        </div>
        <p>{r.basis}</p>
        <EvidenceLink
          id={r.document_id}
          page={r.source_page}
          locator={r.source_locator}
        >
          Consultar fuente
        </EvidenceLink>
      </section>
      <AppliedFilters
        items={[
          { label: "Entidad", value: r.publisher },
          { label: "Mercado", value: r.market },
          { label: "Moneda", value: r.currency },
          { label: "Unidad", value: r.unit },
          { label: "Serie", value: r.basis },
          { label: "Historial", value: history === "all" ? "Completo" : "Últimos 12 meses publicados" },
        ]}
      />
      <section className="chart-panel">
        <h2>Historial de precios</h2>
        <label className="form-field">
          Historial de precios
          <select value={history} onChange={(e) => setHistory(e.target.value)}>
            <option value="recent">Últimos 12 meses publicados</option>
            <option value="all">Todo el historial conservado</option>
          </select>
        </label>
        <p>
          {rows.length} observaciones · {dateLabel(rows[0].observed_on)} a{" "}
          {dateLabel(rows.at(-1)!.observed_on)}
        </p>
        <svg
          viewBox="0 0 720 205"
          className="price-chart"
          role="img"
          aria-label={`Historial de ${r.product_name} en ${r.currency} por ${r.unit}`}
        >
          <path d={path} fill="none" stroke="#22643f" strokeWidth="3" />
          {rows.map((x, i) => (
            <circle
              key={x.observed_on}
              cx={10 + (i / Math.max(1, rows.length - 1)) * 700}
              cy={180 - ((Number(x.price) - low) / span) * 160}
              r="3"
              fill="#22643f"
            >
              <title>
                {dateLabel(x.observed_on)} ·{" "}
                {officialMoney(x.price, x.currency)}
              </title>
            </circle>
          ))}
        </svg>
        <details className="chart-data">
          <summary>Ver datos en tabla</summary>
          <label className="form-field">
            Orden
            <select value={order} onChange={(e) => setOrder(e.target.value)}>
              <option value="price">Precio descendente</option>
              <option value="date">Fecha más reciente</option>
            </select>
          </label>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>
                    {r.currency} / {r.unit}
                  </th>
                  <th>Fuente</th>
                </tr>
              </thead>
              <tbody>
                {[...rows]
                  .sort((a, b) =>
                    order === "price"
                      ? b.price - a.price ||
                        b.observed_on.localeCompare(a.observed_on)
                      : b.observed_on.localeCompare(a.observed_on),
                  )
                  .map((x) => (
                    <tr key={x.observed_on}>
                      <td>{dateLabel(x.observed_on)}</td>
                      <td>{officialMoney(x.price, x.currency)}</td>
                      <td>
                        <EvidenceLink
                          id={x.document_id}
                          page={x.source_page}
                          locator={x.source_locator}
                        >
                          Consultar
                        </EvidenceLink>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
      <details className="panel">
        <summary>Fuente y método del precio</summary>
        <dl className="reference-metadata">
          <div><dt>Entidad</dt><dd>{r.publisher}</dd></div>
          <div><dt>Tipo de precio</dt><dd>{r.basis}</dd></div>
          <div><dt>Mercado</dt><dd>{r.market}</dd></div>
          <div><dt>Moneda y unidad</dt><dd>{r.currency} / {r.unit}</dd></div>
          {Object.entries(r.details)
            .filter(
              ([k, v]) =>
                officialDetailLabels[k] && v !== null && typeof v !== "object",
            )
            .map(([k, v]) => (
              <div key={k}>
                <dt>{officialDetailLabels[k]}</dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
        </dl>
      </details>
    </>
  );
}
