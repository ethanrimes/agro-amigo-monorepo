"use client";
import Link from "next/link";
import { AppliedFilters } from "./AppliedFilters";
import { useEffect, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { SearchBox } from "@/components/ui/SearchBox";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { HierarchicalCategorySelect } from "@/components/ui/HierarchicalCategorySelect";
import { categoryMatches } from "@/lib/category-hierarchy";
import { ReportProductPicture } from "./ReportProductPicture";
import { fold } from "@/lib/planning-math";
import { money, dateLabel, unitLabel } from "@/lib/market-types";
import { normalizeLabel } from "@/lib/label-normalization";
type CityPrice = {
  product_id: string;
  market_id: string;
  market_region: string | null;
  category_path: string[];
  document_id: string;
  source_page: number;
  source_locator: string;
  observed_on: string;
  product_name: string;
  market_name: string;
  display_market_name?: string;
  presentation: string;
  quantity: number;
  source_unit: string;
  round: number;
  round_label: string;
  min_price: number;
  max_price: number;
  unit: string;
  min_unit_price: number | null;
  max_unit_price: number | null;
};
// The server groups only source-verified aliases. Keep the literal market
// name on the evidence link and the canonical label on the browsing filter.
const marketLabel = (row: CityPrice) => row.display_market_name || row.market_name;
export function CityPrices() {
  const { data, loading, error, retry } = useData<CityPrice[]>(
    "/api/planning/regional",
  );
  const [query, setQuery] = useState(""),
    [market, setMarket] = useState(""),
    [category, setCategory] = useState(""),
    [limit, setLimit] = useState(36);
  useEffect(() => {
    setQuery(new URLSearchParams(window.location.search).get("q") || "");
  }, []);
  const rows = (data || []).filter(
    (r) =>
      (!market || marketLabel(r) === market) &&
      categoryMatches(r.category_path.join(" > "), category) &&
      fold(r.product_name + " " + r.presentation).includes(fold(query)),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">DANE · INFORMES POR CIUDADES</span>
          <h1>Precios por ciudad y presentación</h1>
          <p>
            Rangos mínimo y máximo del último informe de cada mercado. Cada
            tarjeta conserva su fecha y ronda.
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="form-grid">
          <SearchBox
            label="Buscar producto por ciudad"
            value={query}
            onChange={(v) => {
              setQuery(v);
              setLimit(36);
            }}
            options={[...new Set((data || []).map((r) => r.product_name))].map(
              (n) => ({ id: n, label: n }),
            )}
          />
          <SearchableSelect
            label="Mercado del informe"
            placeholder="Busca un mercado del informe…"
            emptyLabel="Todos los mercados"
            value={market}
            options={[...new Set((data || []).map(marketLabel))]
              .sort().map((m) => ({ id: m, label: m }))}
            onChange={(id) => { setMarket(id); setLimit(36); }}
            loading={loading}
            error={!!error}
          />
          <HierarchicalCategorySelect
            value={category}
            paths={(data || []).map((row) => row.category_path.join(" > "))}
            onChange={(path) => { setCategory(path); setLimit(36); }}
            loading={loading}
          />
        </div>
        <p>
          El rango principal corresponde al empaque completo. La equivalencia
          por kg, litro o unidad se calcula solo cuando el informe indica su
          contenido. Un cero en una ronda sin cotización no es un precio de
          venta.
        </p>
      </section>
      <AppliedFilters
        items={[
          { label: "Mercado", value: market || "Todos" },
          { label: "Categoría", value: category || "Todas", clear: category ? () => setCategory("") : undefined },
          { label: "Búsqueda", value: query },
          { label: "Fecha", value: "Último informe de cada mercado" },
        ]}
      />
      {loading ? (
        <p role="status">Consultando informes por ciudades…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <p className="results-label">
            {rows.length} rangos de precios ·{" "}
            {[...new Set(rows.map((r) => r.product_name))].length} productos
          </p>
          <div className="input-grid">
            {rows.slice(0, limit).map((r) => (
              <article
                className="panel input-card"
                key={r.document_id + r.source_locator}
              >
                <ReportProductPicture name={r.product_name} />
                <span className="eyebrow">{marketLabel(r)}</span>
                <h2>
                  <Link
                    href={
                      "/product/" +
                      r.product_id +
                      "?" +
                      new URLSearchParams({
                        // The card identifies a specific market. Its verified
                        // department must override another saved department.
                        // An uncurated market uses explicit national scope.
                        region: r.market_region || "",
                        series: "city",
                        market: r.market_id,
                        presentation: r.presentation,
                        units: r.quantity + " " + r.source_unit,
                      })
                    }
                  >
                    {r.product_name}
                  </Link>
                </h2>
                <small>{r.category_path.join(" > ")}</small>
                <p>
                  {normalizeLabel(r.presentation, "presentation")} · {r.quantity} {r.source_unit}
                </p>
                <strong className="input-price">
                  {money(r.min_price)} – {money(r.max_price)}
                </strong>
                <p>Por presentación completa</p>
                {r.min_unit_price !== null && r.max_unit_price !== null && (
                  <p>
                    {money(r.min_unit_price)} – {money(r.max_unit_price)} /{" "}
                    {unitLabel(r.unit)} <small>· equivalente calculado</small>
                  </p>
                )}
                <p>
                  {dateLabel(r.observed_on)} · {r.round_label}
                </p>
                <EvidenceLink
                  id={r.document_id}
                  page={r.source_page}
                  locator={r.source_locator}
                  product={r.product_id}
                  productName={r.product_name}
                  market={r.market_id}
                  marketName={r.market_name}
                  presentation={r.presentation}
                  units={r.quantity + " " + r.source_unit}
                  month={r.observed_on}
                >
                  Consultar fuente · PDF de la ciudad
                </EvidenceLink>
              </article>
            ))}
          </div>
          {rows.length > limit && (
            <div className="load-more">
              <button
                className="button secondary"
                onClick={() => setLimit((n) => n + 36)}
              >
                Ver más rangos
              </button>
            </div>
          )}
          {!rows.length && (
            <p className="empty-state">
              No encontramos precios con estos filtros.
            </p>
          )}
        </>
      )}
    </>
  );
}
