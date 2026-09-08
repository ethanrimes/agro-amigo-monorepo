"use client";
import { use, useEffect, useState } from "react";
import { IoHeartOutline, IoHeart } from "react-icons/io5";
import { CoffeeDetail } from "@/components/explore/CoffeeDetail";
import {
  DetailTabs,
  type InformationMode,
} from "@/components/explore/DetailTabs";
import { SupplyPanel } from "@/components/explore/SupplyPanel";
import {
  AppliedFilters,
  priceSeriesLabel,
} from "@/components/explore/AppliedFilters";
import { MapButton } from "@/components/explore/ColombiaMap";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { CropPicture } from "@/components/marketplace/CropPicture";
import { CatalogBackLink } from "@/components/marketplace/CatalogBackLink";
import { AdditionalProductPrices } from "@/components/marketplace/AdditionalProductPrices";
import type { OfficialPrice } from "@/lib/official-types";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState, Notice } from "@/components/marketplace/Shared";
import { PriceChart } from "@/components/marketplace/PriceChart";
import { MarketList } from "@/components/marketplace/MarketList";
import {
  money,
  dateLabel,
  type Product,
  type MarketPrice,
  type Point,
} from "@/lib/market-types";

type Filters = {
  series: string;
  market: string;
  presentation: string;
  units: string;
  history: string;
};
type Detail = {
  product: Product;
  markets: MarketPrice[];
  history: Point[];
  current: (Point & { market_count: number }) | null;
  classification: string[][];
  additional_references?: OfficialPrice[];
  filters: Filters;
  options: {
    series: string[];
    presentations: string[];
    units: string[];
    markets: { id: string; name: string }[];
  };
};
export default function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return id === "cafe-pergamino-seco" ? (
    <CoffeeDetail />
  ) : (
    <ProductDetail key={id} id={id} />
  );
}
function ProductDetail({ id }: { id: string }) {
  const [mode, setMode] = useState<InformationMode>("price");
  const { region, setRegion, saved, toggleSaved } = usePreferences();
  const [requested, setRequested] = useState<Filters>({
    series: "",
    market: "",
    presentation: "",
    units: "",
    history: "recent",
  });
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.has("region")) setRegion((q.get("region") || "").slice(0, 100));
    setRequested((old) => ({
      ...old,
      ...Object.fromEntries(
        [...q].filter(([k]) =>
          ["series", "market", "presentation", "units"].includes(k),
        ),
      ),
      history: q.get("history") === "all" ? "all" : "recent",
    }));
  }, []);
  const query = new URLSearchParams({ ...requested, region });
  const { data, loading, error, retry } = useData<Detail>(
    `/api/products/${encodeURIComponent(id)}?${query}`,
  );
  const [previous, setPrevious] = useState<Detail | null>(null);
  useEffect(() => {
    if (data) setPrevious(data);
  }, [data]);
  const meta = data || previous;
  const filters =
    data?.filters ||
    ({
      ...previous?.filters,
      ...Object.fromEntries(Object.entries(requested).filter(([, v]) => v)),
      market: requested.market,
    } as Filters);
  function filter(name: keyof Filters, value: string) {
    setRequested((old) => ({
      ...old,
      [name]: value,
      ...(name === "series"
        ? { presentation: "", units: "" }
        : name === "presentation"
          ? { units: "" }
          : {}),
    }));
  }
  const markets = [...(data?.markets || [])].sort(
    (a, b) => b.price - a.price || b.date.localeCompare(a.date),
  );
  const currentMarkets = markets.filter((m) => m.date === data?.current?.date);
  const marketName =
    meta?.options.markets.find((m) => m.id === filters.market)?.name ||
    (filters.market ? "Mercado seleccionado" : "Todos los mercados");
  const city = filters.series === "city";
  return (
    <>
      <CatalogBackLink />
      {meta && (
        <>
          <div className="detail-intro">
            <div className="detail-picture">
              <CropPicture
                imageKey={meta.product.image_key}
                name={meta.product.name}
                category={meta.product.category}
              />
            </div>
            <div>
              <span className="eyebrow">
                {meta.classification.length
                  ? meta.classification
                      .map((path) => path.join(" > "))
                      .join(" · ")
                  : meta.product.category}
              </span>
              <h1>{meta.product.name}</h1>
              <p>DANE · {priceSeriesLabel[filters.series]}</p>
            </div>
            <button
              className="button secondary detail-save"
              aria-pressed={saved.includes(id)}
              onClick={() => toggleSaved(id)}
            >
              {saved.includes(id) ? <IoHeart /> : <IoHeartOutline />}
              {saved.includes(id) ? "Guardado" : "Guardar"}
            </button>
          </div>
          <section className="panel product-price-header">
            <div>
              <span className="eyebrow">PRECIO SEGÚN TU CONSULTA</span>
              <strong
                className="current-product-price"
                data-testid="current-product-price"
              >
                {loading
                  ? "…"
                  : data?.current
                    ? money(data.current.price)
                    : "Sin reporte"}
              </strong>
              <p>
                {filters.presentation} · {filters.units}
              </p>
              {!loading && data?.current && (
                <small>
                  {dateLabel(data.current.date)} · {data.current.market_count}{" "}
                  {data.current.market_count === 1 ? "mercado" : "mercados"}
                </small>
              )}
              {!loading && city && currentMarkets.length === 1 && (
                <p>
                  Rango publicado: {money(currentMarkets[0].min_price!)}–
                  {money(currentMarkets[0].max_price!)}
                </p>
              )}
            </div>
            <p>
              {city
                ? "Punto medio del rango mínimo–máximo por empaque. Para varios mercados, promedio simple de los puntos medios reportados en la fecha indicada."
                : "Promedio de los mercados que reportaron en la fecha indicada, con la misma unidad y tipo de precio."}
            </p>
          </section>
          <p className="field-help">
            Filtros de precios · se aplican a la tarjeta, la gráfica, la
            comparación y el mapa.
          </p>
          <div className="price-filter-grid">
            <label className="form-field">
              Tipo de precio
              <select
                aria-label="Tipo de precio"
                value={filters.series}
                onChange={(e) => filter("series", e.target.value)}
              >
                {meta.options.series.map((s) => (
                  <option value={s} key={s}>
                    {priceSeriesLabel[s]}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Mercado
              <select
                aria-label="Mercado"
                value={filters.market}
                onChange={(e) => filter("market", e.target.value)}
              >
                <option value="">Todos los mercados</option>
                {meta.options.markets.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Presentación
              <select
                aria-label="Presentación"
                value={filters.presentation}
                onChange={(e) => filter("presentation", e.target.value)}
              >
                {meta.options.presentations.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Unidades
              <select
                aria-label="Unidades"
                value={filters.units}
                onChange={(e) => filter("units", e.target.value)}
              >
                {meta.options.units.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          </div>
          <AppliedFilters
            items={[
              {
                label: "Departamento",
                value: region || "Colombia",
                clear: region ? () => setRegion("") : undefined,
              },
              { label: "Fuente", value: priceSeriesLabel[filters.series] },
              { label: "Mercado", value: marketName },
              { label: "Presentación", value: filters.presentation },
              { label: "Unidades", value: filters.units },
            ]}
          />
          <DetailTabs mode={mode} onChange={setMode} />
        </>
      )}
      {loading ? (
        <p className="empty-state" role="status">
          Consultando precios con estos filtros…
        </p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            {mode === "supply" ? (
              <SupplyPanel product={id} name={data.product.name} />
            ) : (
              <>
                <PriceChart
                  key={`${filters.series}:${filters.market}:${filters.presentation}:${filters.units}:${filters.history}`}
                  points={data.history}
                  label="Así ha cambiado el precio"
                  unit={`COP / ${filters.presentation} · ${filters.units}`}
                  allowAll={filters.history === "all"}
                />
                <p className="privacy-note">
                  La gráfica y los mercados usan los filtros mostrados arriba.
                  La cobertura de mercados puede cambiar entre fechas.
                </p>
                <MarketList markets={markets} />
                <div className="detail-actions">
                  <MapButton
                    kind="product"
                    id={id}
                    filters={{ ...filters, region }}
                  />
                  {currentMarkets[0] && (
                    <EvidenceLink
                      id={currentMarkets[0].document_id}
                      page={currentMarkets[0].source_page}
                      locator={currentMarkets[0].source_locator}
                    >
                      Consultar fuente del precio actual
                    </EvidenceLink>
                  )}
                </div>
                <AdditionalProductPrices rows={data.additional_references || []} />
                <Notice>
                  {filters.series === "farmgate"
                    ? "Precio de leche cruda en finca, por litro."
                    : filters.series === "mill"
                      ? "Precio en molino. La fuente publica COP por tonelada; aquí se divide entre 1.000 para mostrar COP por kg."
                      : "Precios de venta mayorista. Cada cotización conserva su presentación, unidades, fecha y fuente."}
                </Notice>
              </>
            )}
          </>
        )
      )}
    </>
  );
}
