"use client";
import { useRef, useState } from "react";
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
import { money, dateLabel } from "@/lib/market-types";
import { fold } from "@/lib/planning-math";
import { normalizeLabel } from "@/lib/label-normalization";
import { quotePresentationOptions } from "@/lib/quote-filter-options";
import type { ComparisonData, ComparisonQuote } from "@/lib/comparison-types";
import { QuoteEvidence, quoteHref } from "./QuoteEvidence";
import styles from "./comparison.module.css";

const quoteKey = (q: ComparisonQuote) => JSON.stringify([
  q.id, q.presentation, q.units, q.series, q.location_id,
  q.date, q.document_id, q.source_locator,
]);

export function MarketPrices({ id, name }: { id: string; name: string }) {
  const [series, setSeries] = useState("");
  const history = "recent";
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [presentation, setPresentation] = useState("");
  const [units, setUnits] = useState("");
  const [selectedQuoteKey, setSelectedQuoteKey] = useState("");
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
        categoryMatches(r.category_path.join(" > "), category) &&
        (!presentation || r.presentation === presentation) &&
        (!units || r.units === units) &&
        fold(r.name).includes(fold(query)),
    )
    .sort((a, b) => b.price - a.price || a.name.localeCompare(b.name, "es"));
  const selectedQuote = rows.find((q) => quoteKey(q) === selectedQuoteKey);
  const visibleRows = rows.slice(0, 6);
  if (selectedQuote && !visibleRows.some((q) => quoteKey(q) === selectedQuoteKey))
    visibleRows.push(selectedQuote);
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
              setSelectedQuoteKey("");
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
              setSelectedQuoteKey("");
            }}
          />
        </label>
        <HierarchicalCategorySelect
          emptyLabel="Todas"
          value={category}
          paths={[...new Set(sourceRows.map((r) => r.a.category_path.join(" > ")))]}
          onChange={(id) => { setCategory(id); setSelectedQuoteKey(""); }}
        />
        <SearchableSelect
          label="Presentación"
          placeholder="Busca una presentación…"
          emptyLabel="Todas"
          value={presentation}
          options={quotePresentationOptions([...new Set(sourceRows.map((r) => r.a.presentation))].sort())}
          onChange={(id) => { setPresentation(id); setUnits(""); setSelectedQuoteKey(""); }}
        />
        <SearchableSelect
          label="Unidades"
          placeholder="Busca unidades…"
          emptyLabel="Todas"
          value={units}
          options={[
            ...new Set(
              sourceRows
                .filter((r) => !presentation || r.a.presentation === presentation)
                .map((r) => r.a.units),
            ),
          ].sort().map((u) => ({ id: u, label: u }))}
          onChange={(id) => { setUnits(id); setSelectedQuoteKey(""); }}
        />
      </div>
      <AppliedFilters
        items={[
          { label: "Mercado", value: name },
          {
            label: "Serie",
            value: priceSeriesLabel[selectedSeries] || selectedSeries,
          },
          { label: "Categoría", value: category || "Todas" },
          { label: "Presentación", value: normalizeLabel(presentation, "presentation") || "Todas" },
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
          {rows.length > 6 && (
            <>
              <p className={styles.note}>
                Se muestran las seis cotizaciones de mayor precio y la cotización elegida.
                Busca entre las {rows.length} combinaciones para consultar otra.
              </p>
              <SearchableSelect
                label="Consultar una cotización de este mercado"
                placeholder="Busca producto, presentación o unidades…"
                value={selectedQuote ? selectedQuoteKey : ""}
                options={rows.map((q) => ({
                  id: quoteKey(q),
                  label: `${q.name} · ${normalizeLabel(q.presentation, "presentation")} · ${q.units}`,
                  detail: `${dateLabel(q.date)} · ${money(q.price)} · ${q.category_path.join(" > ")} · ${q.source_locator}`,
                  searchText: [q.name, q.presentation, q.units, q.category_path.join(" > "), q.date, q.source_locator].join(" "),
                }))}
                onChange={setSelectedQuoteKey}
                emptyLabel="Elige una cotización exacta para verla junto a las seis de mayor precio"
              />
            </>
          )}
          <div className={styles.list}>
            {visibleRows.map((q) => (
              <article
                className={styles.row}
                key={quoteKey(q)}
              >
                <div className={styles.rowHead}>
                  <div>
                    <Link href={quoteHref(q, "markets", history)}>
                      {q.name}
                    </Link>
                    <p>{q.category_path.join(" > ")}</p>
                    <p>
                      {normalizeLabel(q.presentation, "presentation")} · {q.units}
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
              {visibleRows.length} de {rows.length}{" "}
              {rows.length === 1 ? "combinación" : "combinaciones"}
            </span>
          </div>
        </>
      )}
    </section>
  );
}
