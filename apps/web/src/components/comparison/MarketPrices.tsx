"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import {
  AppliedFilters,
  priceSeriesLabel,
} from "@/components/explore/AppliedFilters";
import { money, dateLabel } from "@/lib/market-types";
import { fold } from "@/lib/planning-math";
import type { ComparisonData } from "@/lib/comparison-types";
import { QuoteEvidence, quoteHref } from "./QuoteEvidence";
import styles from "./comparison.module.css";

export function MarketPrices({ id, name }: { id: string; name: string }) {
  const [series, setSeries] = useState("");
  const history = "recent";
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [presentation, setPresentation] = useState("");
  const [units, setUnits] = useState("");
  const [limit, setLimit] = useState(12);
  const params = new URLSearchParams({
    a: id,
    view: "prices",
    series,
    history,
  });
  const { data, loading, error, retry } = useData<ComparisonData>(
    `/api/compare/markets?${params}`,
  );
  const previous = useRef<ComparisonData | null>(null);
  if (data) previous.current = data;
  const metadata = data || previous.current;
  const rows = (data?.rows || [])
    .map((r) => r.a)
    .filter(
      (r) =>
        (!category || r.category_path.join(" > ") === category) &&
        (!presentation || r.presentation === presentation) &&
        (!units || r.units === units) &&
        fold(r.name).includes(fold(query)),
    )
    .sort((a, b) => b.price - a.price || a.name.localeCompare(b.name, "es"));
  const sourceRows = metadata?.rows || [];
  const selectedSeries = series || metadata?.filters.series || "";
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Precios en este mercado</h2>
          <p>Última cotización de cada producto, presentación y unidades.</p>
        </div>
        <Link
          className="button secondary"
          href={`/compare/markets?${new URLSearchParams({ a: id, series: selectedSeries, history, category, presentation, units, q: query })}`}
        >
          Comparar con otro mercado
        </Link>
      </div>
      <div className={styles.controls}>
        <label>
          Tipo de precio
          <select
            value={selectedSeries}
            onChange={(e) => {
              setSeries(e.target.value);
              setCategory("");
              setPresentation("");
              setUnits("");
              setLimit(12);
            }}
          >
            {(metadata?.series || []).map((s) => (
              <option key={s} value={s}>
                {priceSeriesLabel[s] || s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Buscar producto
          <input
            type="search"
            placeholder="Nombre del producto…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(12);
            }}
          />
        </label>
        <label>
          Categoría
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setLimit(12);
            }}
          >
            <option value="">Todas</option>
            {[...new Set(sourceRows.map((r) => r.a.category_path.join(" > ")))]
              .sort()
              .map((c) => (
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
              setLimit(12);
            }}
          >
            <option value="">Todas</option>
            {[...new Set(sourceRows.map((r) => r.a.presentation))]
              .sort()
              .map((p) => (
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
              setLimit(12);
            }}
          >
            <option value="">Todas</option>
            {[
              ...new Set(
                sourceRows
                  .filter(
                    (r) => !presentation || r.a.presentation === presentation,
                  )
                  .map((r) => r.a.units),
              ),
            ]
              .sort()
              .map((u) => (
                <option key={u}>{u}</option>
              ))}
          </select>
        </label>
      </div>
      <AppliedFilters
        items={[
          { label: "Mercado", value: name },
          {
            label: "Serie",
            value: priceSeriesLabel[selectedSeries] || selectedSeries,
          },
          { label: "Categoría", value: category || "Todas" },
          { label: "Presentación", value: presentation || "Todas" },
          { label: "Unidades", value: units || "Todas" },
          { label: "Búsqueda", value: query, clear: () => setQuery("") },
        ]}
      />
      {selectedSeries === "city" && (
        <p className={styles.note}>
          Precio por empaque: punto medio entre mínimo y máximo de la última
          ronda publicada. Cada presentación y cantidad se conserva por
          separado.
        </p>
      )}
      <p className={styles.caption}>
        Precios en COP · ordenados de mayor a menor
      </p>
      {loading ? (
        <p role="status">Consultando todos los precios del mercado…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className={styles.list}>
            {rows.slice(0, limit).map((q) => (
              <article
                className={styles.row}
                key={JSON.stringify([q.id, q.presentation, q.units, q.series])}
              >
                <div className={styles.rowHead}>
                  <div>
                    <Link href={quoteHref(q, "markets", history)}>
                      {q.name}
                    </Link>
                    <p>{q.category_path.join(" > ")}</p>
                    <p>
                      {q.presentation} · {q.units}
                    </p>
                    <small>{dateLabel(q.date)}</small>
                  </div>
                  <div className={styles.difference}>
                    {money(q.price)}
                    {q.series === "city" && (
                      <p className={styles.muted}>
                        {money(q.min_price || q.price)} –{" "}
                        {money(q.max_price || q.price)}
                      </p>
                    )}
                    <QuoteEvidence quote={q} kind="markets" />
                  </div>
                </div>
              </article>
            ))}
          </div>
          {!rows.length && (
            <p className={styles.empty}>
              No hay cotizaciones con estos filtros.
            </p>
          )}
          <div className={styles.expand}>
            <span className={styles.total}>
              {Math.min(limit, rows.length)} de {rows.length} combinaciones
            </span>
            {rows.length > limit && (
              <>
                <button
                  className="button secondary"
                  onClick={() => setLimit((n) => n + 24)}
                >
                  Ver 24 más
                </button>
                <button
                  className="button secondary"
                  onClick={() => setLimit(rows.length)}
                >
                  Expandir lista completa
                </button>
              </>
            )}
            {limit > 12 && (
              <button className="button secondary" onClick={() => setLimit(12)}>
                Mostrar menos
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
