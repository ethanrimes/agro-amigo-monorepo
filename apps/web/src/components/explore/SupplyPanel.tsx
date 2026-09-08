"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppliedFilters } from "./AppliedFilters";
import { IoCubeOutline } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { number, dateLabel } from "@/lib/market-types";
import type { SupplyData } from "@/lib/explore-types";
const monthLabel = (d: string) =>
  new Date(d + "T12:00:00Z").toLocaleDateString("es-CO", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bogota",
  });
export function SupplyPanel({
  product = "",
  market = "",
  name = "este producto",
}: {
  product?: string;
  market?: string;
  name?: string;
}) {
  const [month, setMonth] = useState("");
  const [periods, setPeriods] = useState<SupplyData["history"]>([]);
  const { data, loading, error, retry } = useData<SupplyData>(
    "/api/explore/supply?product=" +
      encodeURIComponent(product) +
      "&market=" +
      encodeURIComponent(market) +
      "&month=" +
      month +
      "&history=all",
  );
  useEffect(() => {
    if (data) setPeriods(data.history);
  }, [data]);
  const controls = (
    <>
      <section
        className="panel price-filter-grid supply-filter-grid"
        aria-label="Filtros de abastecimiento"
      >
        <label className="form-field">
          Mes de consulta
          <select
            value={month || data?.selected_period || ""}
            disabled={loading || !periods.length}
            onChange={(e) => setMonth(e.target.value)}
          >
            {!periods.length && (
              <option value="">Último reporte disponible</option>
            )}
            {[...periods].reverse().map((h) => (
              <option value={h.date} key={h.date}>
                {monthLabel(h.date)}
              </option>
            ))}
          </select>
        </label>
      </section>
      <AppliedFilters
        items={[
          { label: product ? "Producto" : "Mercado", value: name },
          {
            label: "Mes",
            value:
              month || data?.selected_period
                ? monthLabel(month || data!.selected_period!)
                : "Último reporte disponible",
          },
          { label: "Datos", value: "Llegadas reportadas · DANE SIPSA-A" },
        ]}
      />
    </>
  );
  if (loading)
    return (
      <>
        {controls}
        <section className="panel" role="status">
          Consultando abastecimiento…
        </section>
      </>
    );
  if (error)
    return (
      <>
        {controls}
        <ErrorState message={error} retry={retry} />
      </>
    );
  if (!data?.rows.length)
    return (
      <>
        {controls}
        <section className="panel supply-empty">
          <IoCubeOutline />
          <h2>Sin volúmenes reportados para {name}</h2>
          <p>
            La fuente de abastecimiento no tiene una serie comparable para esta
            referencia. Esto no significa que no haya producto.
          </p>
          <p>
            Los nombres, las variedades y el estado del producto deben coincidir
            para comparar cantidades.
          </p>
          <Link className="button secondary" href="/markets">
            Consultar otros mercados
          </Link>
          <EvidenceLink id="supply-2026">
            Consultar fuente de abastecimiento
          </EvidenceLink>
        </section>
      </>
    );
  const first = data.rows.reduce(
      (v, r) => (r.first_reported_on < v ? r.first_reported_on : v),
      data.rows[0].first_reported_on,
    ),
    last = data.rows.reduce(
      (v, r) => (r.observed_on > v ? r.observed_on : v),
      data.rows[0].observed_on,
    );
  const total = data.rows.reduce((s, r) => s + r.quantity_kg, 0),
    max = Math.max(...data.history.map((h) => h.quantity_kg), 1);
  return (
    <div className="supply-content">
      {controls}
      <section className="panel supply-summary">
        <div>
          <span className="eyebrow">ALIMENTOS QUE LLEGARON</span>
          <h2>
            {number(total / 1000)} <small>toneladas</small>
          </h2>
          <p>
            {market
              ? "Llegadas al mercado"
              : "Llegadas a los mercados con reporte"}{" "}
            · DANE SIPSA-A
          </p>
          <p className="field-help">
            Reportes del {dateLabel(first, true)} al {dateLabel(last, true)}.
          </p>
        </div>
      </section>
      <section className="panel">
        <h2>Así cambia el abastecimiento</h2>
        <p className="field-help">
          Toneladas reportadas por mes. Toca una barra para consultar el
          detalle.
        </p>
        <div
          className="supply-bars"
          aria-label="Abastecimiento mensual en toneladas"
        >
          {data.history.map((h) => (
            <button
              className={h.date === data.selected_period ? "selected" : ""}
              key={h.date}
              aria-label={`${monthLabel(h.date)}: ${number(h.quantity_kg / 1000)} toneladas`}
              aria-pressed={h.date === data.selected_period}
              onClick={() => setMonth(h.date)}
            >
              <span className="supply-bar-track">
                <span
                  style={{
                    height: Math.max(2, (h.quantity_kg / max) * 100) + "%",
                  }}
                />
              </span>
              <small>
                {new Date(h.date + "T12:00:00Z").toLocaleDateString("es-CO", {
                  month: "short",
                  year: "2-digit",
                  timeZone: "America/Bogota",
                })}
              </small>
            </button>
          ))}
        </div>
        <p className="privacy-note">
          La cobertura puede cambiar entre meses. Los períodos parciales no se
          completan ni se estiman.
        </p>
      </section>
      <section className="panel">
        <h2>{market ? "Productos que llegaron" : "Llegadas por mercado"}</h2>
        <div className="supply-list">
          {data.rows.map((r) => (
            <article key={r.market_id + r.food_id}>
              <div>
                {market ? (
                  r.product_id ? (
                    <Link href={"/product/" + r.product_id}>{r.food_name}</Link>
                  ) : (
                    <strong>{r.food_name}</strong>
                  )
                ) : (
                  <Link href={"/market/" + r.market_id}>{r.market_name}</Link>
                )}
                <small>
                  {dateLabel(r.first_reported_on, true)} –{" "}
                  {dateLabel(r.observed_on, true)} · {r.reporting_days} días con
                  reporte
                </small>
              </div>
              <div>
                <strong>{number(r.quantity_kg / 1000)} t</strong>
                <EvidenceLink
                  id={r.document_id}
                  product={r.product_id || undefined}
                  market={r.market_id}
                  food={r.food_id}
                  month={r.period_start}
                >
                  Comprobar cantidad
                </EvidenceLink>
              </div>
            </article>
          ))}
        </div>
      </section>
      <p className="notice">
        El abastecimiento mide llegadas reportadas, no existencias disponibles
        ni ofertas de venta. No todos los productos y mercados tienen la misma
        cobertura.
      </p>
    </div>
  );
}
