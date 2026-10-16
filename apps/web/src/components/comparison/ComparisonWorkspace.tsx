"use client";
import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { HierarchicalCategorySelect } from "@/components/ui/HierarchicalCategorySelect";
import { categoryMatches } from "@/lib/category-hierarchy";
import {
  AppliedFilters,
  priceSeriesLabel,
} from "@/components/explore/AppliedFilters";
import { fold } from "@/lib/planning-math";
import { normalizeLabel } from "@/lib/label-normalization";
import { quotePresentationOptions } from "@/lib/quote-filter-options";
import { summarizeComparisons } from "@/lib/comparison-math";
import type { ComparisonData, ComparisonKind, ComparisonRow } from "@/lib/comparison-types";
import { dateLabel } from "@/lib/market-types";
import { ComparisonRowCard } from "./ComparisonRowCard";
import { percentLabel } from "./format";
import styles from "./comparison.module.css";

const comparisonChoiceKey = (row: ComparisonRow) => JSON.stringify([
  row.key, row.a.date, row.a.document_id, row.a.source_locator,
]);

export function ComparisonWorkspace({ kind }: { kind: ComparisonKind }) {
  const initial = useSearchParams();
  const [requested, setRequested] = useState<Record<string, string>>(() =>
    ({ ...Object.fromEntries(initial), history: initial.get("history") === "all" ? "all" : "recent" }),
  );
  const [query, setQuery] = useState(initial.get("q") || "");
  const [category, setCategory] = useState(initial.get("category") || "");
  const [presentation, setPresentation] = useState(
    initial.get("presentation") || "",
  );
  const [units, setUnits] = useState(initial.get("units") || "");
  const [matching, setMatching] = useState("all");
  const [sort, setSort] = useState("difference");
  const [selectedRowKey, setSelectedRowKey] = useState("");
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
    setSelectedRowKey("");
    setCategory("");
    setPresentation("");
    setUnits("");
  };
  const rows = useMemo(
    () =>
      (data?.rows || []).filter(
        (r) =>
          categoryMatches(r.a.category_path.join(" > "), category) &&
          (!presentation || r.a.presentation === presentation) &&
          (!units || r.a.units === units) &&
          (matching !== "matched" || r.b) &&
          fold(
            [
              r.a.name,
              r.a.brand,
              r.a.registration,
              r.a.product_line,
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
  const selectedRow = ordered.find((row) => comparisonChoiceKey(row) === selectedRowKey);
  const visibleRows = ordered.slice(0, 6);
  if (selectedRow && !visibleRows.some((row) => comparisonChoiceKey(row) === selectedRowKey))
    visibleRows.push(selectedRow);
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
    { label: "Historial", value: filters.history === "all" ? "Todo el historial" : "Últimos 12 meses" },
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
        ? metadata?.rows[0]?.a
          ? [metadata.rows[0].a.name, metadata.rows[0].a.product_line && `Línea: ${metadata.rows[0].a.product_line}`]
              .filter(Boolean).join(" · ")
          : filters.product
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
      value: normalizeLabel(presentation, "presentation") || "Todas · comparación por coincidencia exacta",
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
          <SearchableSelect
            label={`A · ${kind === "markets" ? "Mercado base" : "Lugar base"}`}
            placeholder="Busca el lugar base…"
            emptyLabel="Selecciona un lugar"
            value={selectedA}
            options={locations.map((l) => ({ id: l.id, label: l.name }))}
            selectedLabel={metadata?.a_name}
            onChange={(id) => {
              setFilter("a", id);
              if (selectedB === id) setRequested((current) => ({ ...current, b: "__national__" }));
            }}
            allowClear={false}
            loading={loading && !metadata}
            error={!!error && !metadata}
          />
          <SearchableSelect
            label="B · Comparar con"
            placeholder="Busca el lugar de comparación…"
            value={selectedB}
            options={[
              { id: "__national__", label: "Promedio de Colombia" },
              ...locations.filter((l) => l.id !== selectedA)
                .map((l) => ({ id: l.id, label: l.name })),
            ]}
            onChange={(id) => setFilter("b", id)}
            allowClear={false}
            loading={loading && !metadata}
            error={!!error && !metadata}
          />
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
                  setSelectedRowKey("");
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
                setSelectedRowKey("");
              }}
              placeholder={
                kind === "markets"
                  ? "Limón, papa, arroz…"
                  : "Urea, marca, registro…"
              }
            />
          </label>
          <HierarchicalCategorySelect
            value={category}
            paths={categories}
            onChange={(id) => { setCategory(id); setSelectedRowKey(""); }}
          />
          <SearchableSelect
            label="Presentación"
            placeholder="Busca una presentación…"
            emptyLabel="Todas las presentaciones"
            value={presentation}
            options={quotePresentationOptions(presentations)}
            onChange={(id) => { setPresentation(id); setUnits(""); setSelectedRowKey(""); }}
          />
          <SearchableSelect
            label="Unidades"
            placeholder="Busca unidades…"
            emptyLabel="Todas las unidades"
            value={units}
            options={unitOptions.map((u) => ({ id: u, label: u }))}
            onChange={(id) => { setUnits(id); setSelectedRowKey(""); }}
          />
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
                  <b>{summary.matched}</b>{" "}
                  {summary.matched === 1 ? "combinación comparable" : "combinaciones comparables"}
                </p>
                <p className={styles.muted}>
                  {summary.unmatched} sin una cotización equivalente en B ·{" "}
                  {rows.length}{" "}
                  {rows.length === 1 ? "combinación" : "combinaciones"} de A bajo los filtros
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
                      setSelectedRowKey("");
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
              {ordered.length > 6 && (
                <>
                  <p className={styles.note}>
                    Se muestran seis combinaciones según el orden elegido y la combinación seleccionada.
                    Busca entre las {ordered.length} combinaciones para consultar otra.
                  </p>
                  <SearchableSelect
                    label="Consultar una combinación de la comparación"
                    placeholder="Busca producto, marca, presentación o unidades…"
                    value={selectedRow ? selectedRowKey : ""}
                    options={ordered.map((row) => ({
                      id: comparisonChoiceKey(row),
                      label: [row.a.name, row.a.product_line, normalizeLabel(row.a.presentation, "presentation"), row.a.units]
                        .filter(Boolean).join(" · "),
                      detail: [row.a.brand, row.a.registration && `ICA ${row.a.registration}`,
                        dateLabel(row.a.date), percentLabel(row.percent), row.a.source_locator]
                        .filter(Boolean).join(" · "),
                      searchText: [row.a.name, row.a.product_line, row.a.brand, row.a.registration,
                        row.a.presentation, row.a.units, row.a.category_path.join(" > "),
                        row.a.date, row.a.document_id, row.a.source_locator].filter(Boolean).join(" "),
                    }))}
                    onChange={setSelectedRowKey}
                    emptyLabel="Elige una combinación exacta para verla junto a las seis primeras"
                  />
                </>
              )}
              <div className={styles.list}>
                {visibleRows.map((row) => (
                  <ComparisonRowCard key={comparisonChoiceKey(row)} row={row} context={data} />
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
                  {visibleRows.length} de {rows.length}{" "}
                  {rows.length === 1 ? "combinación" : "combinaciones"}
                </span>
              </div>
            </section>
          </>
        )
      )}
    </>
  );
}
