"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState, LoadingCards } from "@/components/marketplace/Shared";
import { SearchBox } from "@/components/ui/SearchBox";
import { MapButton } from "@/components/explore/ColombiaMap";
import { photoFor } from "@/lib/images";
import { fold } from "@/lib/planning-math";
import { money, dateLabel } from "@/lib/market-types";
import type { InputPrice } from "@/lib/planning-types";
function Inputs() {
  const q = useSearchParams(),
    router = useRouter(),
    { region } = usePreferences();
  const [department, setDepartment] = useState(q.get("department") || region),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState("Todos"),
    [limit, setLimit] = useState(24);
  const { data, loading, error, retry } = useData<InputPrice[]>(
    "/api/planning/inputs",
  );
  const departments = [
    ...new Set((data || []).map((i) => i.department)),
  ].sort();
  const available = (data || []).filter(
    (i) =>
      (!department || fold(i.department) === fold(department)) &&
      (category === "Todos" || i.category === category),
  );
  const grouped = new Map<string, InputPrice>();
  for (const i of [...available].sort(
    (a, b) => b.observed_on.localeCompare(a.observed_on) || a.price - b.price,
  ))
    if (!grouped.has(i.id)) grouped.set(i.id, i);
  const unique = [...grouped.values()].sort(
    (a, b) =>
      Number(!/urea|cal agricola|15-15-15|abono organico/.test(fold(a.name))) -
        Number(
          !/urea|cal agricola|15-15-15|abono organico/.test(fold(b.name)),
        ) || a.name.localeCompare(b.name),
  );
  const rows = unique.filter((i) =>
    fold(i.name + " " + i.presentation).includes(fold(query)),
  );
  return (
    <>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">PARA CUIDAR TU CULTIVO</span>
          <h1>Insumos agrícolas</h1>
          <p>Compara referencias por presentación y departamento.</p>
        </div>
        <MapButton kind="input" />
      </div>
      <div className="catalog-controls">
        <SearchBox
          label="Buscar insumo"
          placeholder="Urea, cal, abono orgánico…"
          value={query}
          onChange={(v) => {
            setQuery(v);
            setLimit(24);
          }}
          options={unique.map((i) => ({
            id: i.id,
            label: i.name,
            detail: i.presentation,
          }))}
          onSelect={(i) =>
            router.push(
              "/insumo/" +
                i.id +
                "?department=" +
                encodeURIComponent(department),
            )
          }
        />
        <label className="region-field">
          <span>Departamento</span>
          <select
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setLimit(24);
            }}
          >
            <option value="">Toda Colombia</option>
            {department && !departments.includes(department) && (
              <option>{department}</option>
            )}
            {departments.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="category-filters">
        {["Todos", "Fertilizantes y enmiendas", "Bioinsumos"].map((c) => (
          <button
            key={c}
            aria-pressed={category === c}
            className={category === c ? "active" : ""}
            onClick={() => {
              setCategory(c);
              setLimit(24);
            }}
          >
            {c}
          </button>
        ))}
      </div>
      {loading ? (
        <LoadingCards />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>{rows.length} insumos y presentaciones</span>
            <Link href="/plan?tab=budget">Ir a mi presupuesto →</Link>
          </div>
          <div className="input-grid">
            {rows.slice(0, limit).map((i) => {
              const p = photoFor(
                i.name,
                i.category + " " + i.presentation,
                "input",
              );
              return (
                <Link
                  href={
                    "/insumo/" +
                    i.id +
                    "?department=" +
                    encodeURIComponent(department || i.department)
                  }
                  className="input-catalog-card"
                  key={i.id}
                >
                  <div className="input-photo">
                    <img src={p.src} alt={p.alt} loading="lazy" />
                    <small>Imagen ilustrativa</small>
                  </div>
                  <div>
                    <span className="eyebrow">{i.category}</span>
                    <h2>{i.name}</h2>
                    <p>{i.presentation}</p>
                    <strong className="input-price">{money(i.price)}</strong>
                    <small>
                      {i.department} · {dateLabel(i.observed_on, true)}
                    </small>
                    <span className="input-card-action">
                      Ver precios y cobertura →
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
          {!rows.length && (
            <div className="empty-state">
              <h2>No encontramos ese insumo</h2>
              <p>Prueba otro nombre o departamento.</p>
            </div>
          )}
          {rows.length > limit && (
            <div className="load-more">
              <button
                className="button secondary"
                onClick={() => setLimit((n) => n + 24)}
              >
                Ver más insumos
              </button>
            </div>
          )}
        </>
      )}
      <p className="notice">
        DANE SIPSA-I · Promedios departamentales. Consulta la presentación y
        confirma tu cotización antes de comprar.
      </p>
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
