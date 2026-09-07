"use client";
import { useState } from "react";
import { SearchBox } from "@/components/ui/SearchBox";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { money, dateLabel } from "@/lib/market-types";
import { fold } from "@/lib/planning-math";
type Daily = {
  observed_on: string;
  product_name: string;
  market_name: string;
  price: number;
  change_percent: number | null;
  document_id: string;
  source_page: number;
};
export default function DailyPage() {
  const { data, loading, error, retry } = useData<Daily[]>(
      "/api/planning/daily",
    ),
    [product, setProduct] = useState(""),
    [market, setMarket] = useState("");
  const rows = (data || [])
    .filter(
      (r) =>
        fold(r.product_name).includes(fold(product)) &&
        (!market || r.market_name === market),
    )
    .sort(
      (a, b) =>
        a.product_name.localeCompare(b.product_name, "es") || b.price - a.price,
    );
  return (
    <>
      <Link href="/products" className="back-link">
        ← Productos e historia mensual
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">UNA REFERENCIA MÁS CERCANA A TU VENTA</span>
          <h1>El último boletín diario</h1>
          <p>
            DANE SIPSA ·{" "}
            {data?.[0]
              ? dateLabel(data[0].observed_on)
              : "Consulta la fecha de publicación"}{" "}
            · COP por kilogramo
          </p>
        </div>
      </div>
      <section className="panel">
        <p>
          Precios mayoristas reportados ese día. Confirma el pago en finca, la
          variedad y los gastos antes de acordar una venta.
        </p>
        <div className="form-grid">
          <div className="form-field">
            <span>Buscar producto en el boletín</span>
            <SearchBox
              label="Buscar producto en el boletín"
              value={product}
              onChange={setProduct}
              options={[
                ...new Set((data || []).map((r) => r.product_name)),
              ].map((n) => ({ id: n, label: n }))}
            />
          </div>
          <label className="form-field">
            Plaza del boletín
            <select value={market} onChange={(e) => setMarket(e.target.value)}>
              <option value="">Todas las plazas</option>
              {Array.from(new Set((data || []).map((r) => r.market_name)))
                .sort()
                .map((m) => (
                  <option key={m}>{m}</option>
                ))}
            </select>
          </label>
        </div>
        <p className="field-help">
          * La variedad predominante puede cambiar entre mercados. No se combina
          este boletín con la serie mensual de una variedad específica. Sin dato
          significa que la entidad no lo reportó.
        </p>
      </section>
      {loading ? (
        <p role="status">Consultando el boletín…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <p>{rows.length} referencias</p>
          <div className="input-grid">
            {rows.map((r) => (
              <article
                className="panel input-card"
                key={r.product_name + r.market_name}
              >
                <span className="eyebrow">{r.market_name}</span>
                <h2>{r.product_name}</h2>
                <strong className="input-price">
                  {money(r.price)} <small>/ kg</small>
                </strong>
                <p>
                  {r.change_percent === null
                    ? "Sin variación reportada"
                    : `${r.change_percent > 0 ? "+" : ""}${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(r.change_percent)} % frente al anterior día de mercado`}
                </p>
                <EvidenceLink id={r.document_id} page={r.source_page}>
                  Comprobar este precio
                </EvidenceLink>
              </article>
            ))}
          </div>
          {!rows.length && (
            <p className="empty-state">
              No hay referencias para esta búsqueda. Prueba otra plaza o
              producto.
            </p>
          )}
        </>
      )}
      <section className="panel">
        <h2>¿Cuánto producto llegó a las plazas?</h2>
        <p>
          El mismo boletín incluye el abastecimiento de alimentos y sus
          variaciones. Son entradas reportadas, no inventario disponible para
          comprar.
        </p>
        {data?.[0] && (
          <EvidenceLink
            id={"daily-" + data[0].observed_on + "-bulletin"}
            page={4}
          >
            Ver abastecimiento en el boletín DANE
          </EvidenceLink>
        )}
        <Link className="evidence-link" href="/offers">
          Comparar mis cotizaciones y gastos →
        </Link>
      </section>
    </>
  );
}
