"use client";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { fold } from "@/lib/planning-math";
import { money, dateLabel, number } from "@/lib/market-types";
import type { InputPrice, Municipality } from "@/lib/planning-types";
function Inputs() {
  const q = useSearchParams(),
    { region } = usePreferences();
  const [department, setDepartment] = useState(q.get("department") || region),
    [query, setQuery] = useState(""),
    [more, setMore] = useState(false);
  const places = useData<Municipality[]>("/api/planning/municipalities"),
    data = useData<InputPrice[]>(
      "/api/planning/inputs?department=" + encodeURIComponent(department),
    );
  const filtered = useMemo(
    () =>
      data.data?.filter((r) =>
        fold(r.name + " " + r.category).includes(fold(query)),
      ) || [],
    [data.data, query],
  );
  return (
    <>
      <Link className="back-link" href="/plan?tab=budget">
        ← Volver a mis cuentas
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ACTUALIZA TU PRESUPUESTO</span>
          <h1>¿Cómo están los insumos?</h1>
          <p>
            Precios de referencia por presentación y departamento. Confirma tu
            cotización antes de comprar.
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="form-grid">
          <label className="form-field">
            Departamento de consulta
            <select
              value={department}
              onChange={(e) => {
                setDepartment(e.target.value);
                setMore(false);
              }}
            >
              <option value="">Toda Colombia</option>
              {[...new Set(places.data?.map((m) => m.department) || [])]
                .sort()
                .map((d) => (
                  <option key={d}>{d}</option>
                ))}
            </select>
          </label>
          <label className="form-field">
            Buscar insumo
            <input
              type="search"
              placeholder="Urea, cal, fertilizante…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setMore(false);
              }}
            />
          </label>
        </div>
        <p className="privacy-note">
          DANE SIPSA-I · Fertilizantes, enmiendas y bioinsumos. La presencia de
          un producto en la fuente no recomienda usarlo ni establece una dosis.
        </p>
        <EvidenceLink id="input-index" page={2}>
          Consultar el boletín de variación de costos
        </EvidenceLink>
      </section>
      {data.loading ? (
        <p role="status">Consultando precios de insumos…</p>
      ) : data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : (
        <>
          <p>{number(filtered.length)} referencias encontradas</p>
          <div className="input-grid">
            {filtered.slice(0, more ? undefined : 18).map((r) => (
              <article className="panel input-card" key={r.id + r.department}>
                <span className="eyebrow">{r.category}</span>
                <h3>{r.name}</h3>
                <p>
                  {r.presentation} · {r.department}
                </p>
                <strong className="input-price">{money(r.price)}</strong>
                <small>
                  Promedio departamental · {dateLabel(r.observed_on)}
                </small>
                {r.previous_price && (
                  <p className="input-change">
                    {r.price >= r.previous_price ? "Subió" : "Bajó"}{" "}
                    {number(Math.abs(r.price / r.previous_price - 1) * 100)} %
                    frente al mes anterior.
                  </p>
                )}
                <EvidenceLink
                  id={r.document_id}
                  input={r.id}
                  department={r.department}
                >
                  Ver precio y fila original
                </EvidenceLink>
              </article>
            ))}
          </div>
          {!filtered.length && (
            <div className="empty-state">
              <h3>No encontramos esa referencia</h3>
              <p>
                Prueba otro nombre o departamento. No todos los insumos tienen
                cobertura en cada zona.
              </p>
            </div>
          )}
          {filtered.length > 18 && (
            <button
              className="button secondary show-more"
              onClick={() => setMore(!more)}
            >
              {more ? "Mostrar menos" : "Ver todas las referencias"}
            </button>
          )}
        </>
      )}
    </>
  );
}
export default function InputsPage() {
  return (
    <Suspense fallback={<p>Cargando insumos…</p>}>
      <Inputs />
    </Suspense>
  );
}
