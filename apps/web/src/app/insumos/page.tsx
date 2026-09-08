"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState, LoadingCards } from "@/components/marketplace/Shared";
import { SearchBox } from "@/components/ui/SearchBox";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
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
    [limit, setLimit] = useState(24),
    [scope, setScope] = useState(q.get("scope") || "department");
  const historical = false;
  const { data, loading, error, retry } = useData<InputPrice[]>(
    "/api/planning/inputs?grouped=true&department=" +
      encodeURIComponent(department) +
      "&scope=" +
      scope +
      (historical ? "&history=all" : ""),
  );
  const { data: places } = useData<{ department: string }[]>(
    "/api/planning/municipalities",
  );
  const departments = [
    ...new Set((places || []).map((i) => i.department)),
  ].sort();
  const target = (i: InputPrice) =>
    "/insumo/" +
    i.id +
    "?" +
    new URLSearchParams({
      department: i.department,
      municipality: i.municipality || "",
      scope,
      history: historical ? "all" : "recent",
    }).toString();
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
    fold(
      i.name +
        " " +
        i.presentation +
        " " +
        i.brand +
        " " +
        i.registration +
        " " +
        i.category,
    ).includes(fold(query)),
  );
  return (
    <>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">INSUMOS Y FACTORES DE PRODUCCIÓN</span>
          <h1>Insumos agropecuarios</h1>
          <p>
            Consulta insumos agrícolas, pecuarios y servicios por presentación y
            ubicación.
          </p>
        </div>
        <div className="detail-actions">
          <MapButton
            kind="input"
            filters={{
              scope,
              region: department,
              category: category === "Todos" ? "" : category,
              query,
              history: historical ? "all" : "recent",
            }}
          />
          <Link
            className="button secondary"
            href={
              "/compare/inputs?" +
              new URLSearchParams({
                department,
                scope,
                history: historical ? "all" : "recent",
                category: category === "Todos" ? "" : category,
                q: query,
              })
            }
          >
            Comparar ubicaciones →
          </Link>
        </div>
      </div>
      <AppliedFilters
        items={[
          {
            label: "Cobertura",
            value:
              scope === "municipality" ? "Municipio" : "Promedio departamental",
          },
          { label: "Departamento", value: department || "Colombia" },
          { label: "Categoría", value: category },
          { label: "Búsqueda", value: query },
        ]}
      />
      <p>
        <Link href="/data-references" className="button secondary">
          Resúmenes de insumos y tarifas eléctricas →
        </Link>
      </p>
      <div className="catalog-controls">
        <label className="region-field">
          <span>Cobertura del precio</span>
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              setCategory("Todos");
              setLimit(24);
            }}
          >
            <option value="department">Promedio por departamento</option>
            <option value="municipality">Precio por municipio</option>
          </select>
        </label>
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
          onSelect={(option) => {
            const i = unique.find((i) => i.id === option.id);
            if (i) router.push(target(i));
          }}
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
        {["Todos", ...new Set((data || []).map((i) => i.category))].map((c) => (
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
                  href={target(i)}
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
                    {i.brand && <small>{i.brand}</small>}
                    <strong className="input-price">{money(i.price)}</strong>
                    <small>
                      {i.municipality ? i.municipality + ", " : ""}
                      {i.department} · {dateLabel(i.observed_on)}
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
        DANE SIPSA-I ·{" "}
        {scope === "municipality"
          ? "Precios municipales"
          : "Promedios departamentales"}
        . Consulta la fecha, presentación y confirma tu cotización antes de
        comprar.
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
