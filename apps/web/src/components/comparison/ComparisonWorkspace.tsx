"use client";
import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import {
  AppliedFilters,
  priceSeriesLabel,
} from "@/components/explore/AppliedFilters";
import { fold } from "@/lib/planning-math";
import { summarizeComparisons } from "@/lib/comparison-math";
import type { ComparisonData, ComparisonKind } from "@/lib/comparison-types";
import { ComparisonRowCard } from "./ComparisonRowCard";
import { percentLabel } from "./format";
import styles from "./comparison.module.css";

export function ComparisonWorkspace({ kind }: { kind: ComparisonKind }) {
  const initial = useSearchParams();
  const [requested, setRequested] = useState<Record<string, string>>(() =>
    ({ ...Object.fromEntries(initial), history: "recent" }),
  );
  const [query, setQuery] = useState(initial.get("q") || "");
  const [category, setCategory] = useState(initial.get("category") || "");
  const [presentation, setPresentation] = useState(
    initial.get("presentation") || "",
  );
  const [units, setUnits] = useState(initial.get("units") || "");
  const [matching, setMatching] = useState("all");
  const [sort, setSort] = useState("difference");
  const [limit, setLimit] = useState(20);
  const params = new URLSearchParams(requested);
  const { data, loading, error, retry } = useData<ComparisonData>(
    `/api/compare/${kind}?${params}`,
  );
  const previous = useRef<ComparisonData | null>(null);
  if (data) previous.current = data;
  const metadata = data || previous.current;
  const filters = data
    ? { ...requested, ...data.filters }
    : { ...metadata?.filters, ...requested };
  const setFilter = (key: string, value: string) => {
    setRequested((current) => ({ ...current, [key]: value }));
    setLimit(20);
    setCategory("");
    setPresentation("");
    setUnits("");
  };
  const rows = useMemo(
    () =>
      (data?.rows || []).filter(
        (r) =>
          (!category || r.a.category_path.join(" > ") === category) &&
          (!presentation || r.a.presentation === presentation) &&
          (!units || r.a.units === units) &&
          (matching !== "matched" || r.b) &&
          fold(
            [
              r.a.name,
              r.a.brand,
              r.a.registration,
              r.a.presentation,
              ...r.a.category_path,
            ].join(" "),
          ).includes(fold(query)),
      ),
    [data, category, presentation, units, matching, query],
  );
  const summary = summarizeComparisons(rows);
  const ordered = [...rows].sort((a, b) =>
    sort === "price-a"
      ? b.a.price - a.a.price
      : sort === "price-b"
        ? (b.b?.price || 0) - (a.b?.price || 0)
        : sort === "name"
          ? a.a.name.localeCompare(b.a.name, "es")
          : (b.percent ?? -Infinity) - (a.percent ?? -Infinity),
  );
  const locations = (metadata?.locations || []).filter(
    (l) => !l.series || l.series.includes(filters.series || ""),
  );
  const selectedA = filters.a || "";
  const selectedB = filters.b || "__national__";
  const categories = [
    ...new Set(
      (metadata?.rows || []).map((r) => r.a.category_path.join(" > ")),
    ),
  ].sort();
  const presentations = [
    ...new Set((metadata?.rows || []).map((r) => r.a.presentation)),
  ].sort();
  const unitOptions = [
    ...new Set(
      (metadata?.rows || [])
        .filter((r) => !presentation || r.a.presentation === presentation)
        .map((r) => r.a.units),
    ),
  ].sort();
  const groupCategories = summary.summaries.filter((g) => !g.subcategory);
  const scopeName =
    filters.scope === "municipality" ? "Municipios" : "Departamentos";
  const filtersForDisplay = [
    {
      label: "A · base",
      value:
        locations.find((l) => l.id === selectedA)?.name ||
        metadata?.a_name ||
        "Cargando",
    },
    {
      label: "B",
      value:
        selectedB === "__national__"
          ? "Promedio de Colombia"
          : locations.find((l) => l.id === selectedB)?.name || "",
    },
    {
      label: kind === "markets" ? "Serie" : "Cobertura",
      value:
        kind === "markets"
          ? priceSeriesLabel[filters.series || ""] || filters.series || ""
          : scopeName,
    },
    {
      label: "Fechas",
      value:
        filters.dates === "same"
          ? "Solo fechas iguales"
          : "Última fecha de cada lugar",
    },
    {
      label: "Producto seleccionado",
      value: filters.product
        ? metadata?.rows[0]?.a.name || filters.product
        : "",
      clear: () => setFilter("product", ""),
    },
    {
      label: "Categoría",
      value: category || "Todas",
      ...(category ? { clear: () => setCategory("") } : {}),
    },
    {
      label: "Presentación",
      value: presentation || "Todas · comparación por coincidencia exacta",
      ...(presentation ? { clear: () => setPresentation("") } : {}),
    },
    {
      label: "Unidades",
      value: units || "Todas · comparación por coincidencia exacta",
      ...(units ? { clear: () => setUnits("") } : {}),
    },
    { label: "Búsqueda", value: query, clear: () => setQuery("") },
    {
      label: "Filas",
      value:
        matching === "matched"
          ? "Solo coincidencias"
          : "Todos los productos de A",
    },
  ];
  return (
    <>
      <Link
        className="back-link"
        href={kind === "markets" ? "/markets" : "/insumos"}
      >
        ← {kind === "markets" ? "Mercados" : "Insumos"}
      </Link>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">PRECIOS COMPARABLES</span>
          <h1>
            {kind === "markets" ? "Comparar mercados" : "Comparar insumos"}
          </h1>
          <p>
            Compara el mismo producto, presentación y unidades entre dos lugares
            o frente al promedio de Colombia.
          </p>
        </div>
      </div>
      <section className="panel" aria-label="Filtros de comparación">
        <div className={styles.controls}>
          <label>
            A · {kind === "markets" ? "Mercado base" : "Lugar base"}
            <select
              value={selectedA}
              onChange={(e) => setFilter("a", e.target.value)}
            >
              <option value="" disabled>
                Selecciona un lugar
              </option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            B · Comparar con
            <select
              value={selectedB}
              onChange={(e) => setFilter("b", e.target.value)}
            >
              <option value="__national__">Promedio de Colombia</option>
              {locations
                .filter((l) => l.id !== selectedA)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
            </select>
          </label>
          {kind === "markets" ? (
            <label>
              Tipo de precio
              <select
                value={filters.series || metadata?.series[0] || ""}
                onChange={(e) => setFilter("series", e.target.value)}
              >
                {(metadata?.series || []).map((s) => (
                  <option key={s} value={s}>
                    {priceSeriesLabel[s] || s}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              Cobertura
              <select
                value={filters.scope || "department"}
                onChange={(e) => {
                  const scope = e.target.value;
                  setRequested((current) => ({
                    ...current,
                    scope,
                    a: "",
                    b: "__national__",
                    department: "",
                    municipality: "",
                  }));
                  setCategory("");
                  setPresentation("");
                  setUnits("");
                  setLimit(20);
                }}
              >
                <option value="department">Promedios por departamento</option>
                <option value="municipality">Precios por municipio</option>
              </select>
            </label>
          )}
          <label>
            Fechas a comparar
            <select
              value={filters.dates || "latest"}
              onChange={(e) => setFilter("dates", e.target.value)}
            >
              <option value="latest">Última fecha de cada lugar</option>
              <option value="same">Solo fechas iguales</option>
            </select>
          </label>
          <label>
            Buscar {kind === "markets" ? "producto" : "insumo, marca o ICA"}
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setLimit(20);
              }}
              placeholder={
                kind === "markets"
                  ? "Limón, papa, arroz…"
                  : "Urea, marca, registro…"
              }
            />
          </label>
          <label>
            Categoría
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setLimit(20);
              }}
            >
              <option value="">Todas las categorías</option>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Presentación
            <select
              value={presentation}
              onChange={(e) => {
                setPresentation(e.target.value);
                setUnits("");
                setLimit(20);
              }}
            >
              <option value="">Todas las presentaciones</option>
              {presentations.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            Unidades
            <select
              value={units}
              onChange={(e) => {
                setUnits(e.target.value);
                setLimit(20);
              }}
            >
              <option value="">Todas las unidades</option>
              {unitOptions.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
        </div>
        <AppliedFilters items={filtersForDisplay} />
        <p className={styles.note}>
          La diferencia es (precio B − precio A) ÷ precio A × 100. Un valor
          positivo significa que B cuesta más. Cada coincidencia pesa lo mismo
          en el promedio; las presentaciones se comparan por separado.
          {kind === "inputs" &&
            " También deben coincidir la identidad comercial, la marca y el registro ICA, cuando se publican."}
        </p>
        <p className={styles.note}>
          Colombia es el promedio simple de los últimos precios disponibles por{" "}
          {kind === "markets"
            ? "mercado"
            : filters.scope === "municipality"
              ? "municipio"
              : "departamento"}
          , incluido A. Se necesita al menos otro lugar con la misma
          combinación. No es un precio nacional oficial ponderado.{" "}
          {filters.dates === "same"
            ? "Solo se incluyen últimas cotizaciones con la misma fecha que A."
            : "Las fechas pueden diferir: revisa las fechas de cada fila."}{" "}
          {kind === "markets" &&
            filters.series === "city" &&
            "En los informes por ciudad, el precio es el punto medio entre mínimo y máximo de la última ronda publicada."}
        </p>
      </section>
      {loading ? (
        <p className={styles.status} role="status">
          Calculando coincidencias y precios…
        </p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <section
              className={styles.summary}
              aria-label="Resultado de la comparación"
            >
              <div>
                <span>Promedio de diferencias · B frente a A</span>
                <strong
                  className={
                    summary.percent !== null && summary.percent > 0
                      ? styles.up
                      : styles.down
                  }
                >
                  {percentLabel(summary.percent)}
                </strong>
              </div>
              <div>
                <p>
                  <b>{summary.matched}</b> combinaciones comparables
                </p>
                <p className={styles.muted}>
                  {summary.unmatched} sin una cotización equivalente en B ·{" "}
                  {rows.length} combinaciones de A bajo los filtros
                </p>
              </div>
            </section>
            {!!groupCategories.length && (
              <section aria-label="Promedios por categoría">
                <h2>Comparación por categoría</h2>
                <div className={styles.groups}>
                  {groupCategories.map((g) => (
                    <details className={styles.group} key={g.category}>
                      <summary>
                        {g.category} <b>{percentLabel(g.percent)}</b>
                      </summary>
                      <p className={styles.muted}>
                        {g.count} coincidencias · promedio simple de diferencias
                      </p>
                      <ul>
                        {summary.summaries
                          .filter(
                            (s) => s.category === g.category && s.subcategory,
                          )
                          .map((s) => (
                            <li key={s.subcategory}>
                              <b>{s.subcategory}</b>: {percentLabel(s.percent)}{" "}
                              · {s.count} coincidencias
                            </li>
                          ))}
                      </ul>
                    </details>
                  ))}
                </div>
              </section>
            )}
            <section className="panel">
              <p className={styles.caption}>
                Precios en pesos colombianos (COP), por la presentación y
                unidades de cada fila.
              </p>
              <div className={styles.toolbar}>
                <h2>Producto por producto</h2>
                <label>
                  Mostrar
                  <select
                    value={matching}
                    onChange={(e) => {
                      setMatching(e.target.value);
                      setLimit(20);
                    }}
                  >
                    <option value="all">Todos los productos de A</option>
                    <option value="matched">Solo coincidencias</option>
                  </select>
                </label>
                <label>
                  Orden
                  <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="difference">
                      Mayor diferencia % primero
                    </option>
                    <option value="price-a">Mayor precio de A primero</option>
                    <option value="price-b">Mayor precio de B primero</option>
                    <option value="name">Nombre A–Z</option>
                  </select>
                </label>
              </div>
              <div className={styles.list}>
                {ordered.slice(0, limit).map((row) => (
                  <ComparisonRowCard key={row.key} row={row} context={data} />
                ))}
              </div>
              {!rows.length && (
                <div className={styles.empty}>
                  No hay productos que coincidan con estos filtros. Cambia la
                  búsqueda, la presentación o el lugar base.
                </div>
              )}
              <div className={styles.expand}>
                <span className={styles.total}>
                  {Math.min(limit, rows.length)} de {rows.length} combinaciones
                </span>
                {rows.length > limit && (
                  <>
                    <button
                      className="button secondary"
                      onClick={() => setLimit((n) => n + 40)}
                    >
                      Ver 40 más
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => setLimit(rows.length)}
                    >
                      Expandir lista completa
                    </button>
                  </>
                )}
                {limit > 20 && (
                  <button
                    className="button secondary"
                    onClick={() => setLimit(20)}
                  >
                    Mostrar menos
                  </button>
                )}
              </div>
            </section>
          </>
        )
      )}
    </>
  );
}
