"use client";
import { use, useEffect, useMemo, useState } from "react";
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
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { quoteMarketOptions, quotePresentationOptions, type QuoteMarketChoice } from "@/lib/quote-filter-options";
import { marketReportsForUnits, resolveProductFilterDimensions,
  type ProductFilterDimensions } from "@/lib/product-filter-dimensions";
import { normalizeLabel } from "@/lib/label-normalization";
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
  region?: string;
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
    markets: QuoteMarketChoice[];
  };
  option_dimensions?: ProductFilterDimensions;
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
  const { region, setRegion, ready: preferencesReady, saved, toggleSaved } = usePreferences();
  const [filtersReady, setFiltersReady] = useState(false);
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
    setFiltersReady(true);
  }, []);
  const query = new URLSearchParams({ ...requested, region });
  const { data, loading, error, retry } = useData<Detail>(
    filtersReady && preferencesReady ? `/api/products/${encodeURIComponent(id)}?${query}` : null,
  );
  const [previous, setPrevious] = useState<Detail | null>(null);
  useEffect(() => {
    if (data) setPrevious(data);
  }, [data]);
  const scopedPrevious = previous?.product.id === id &&
    (previous.option_dimensions?.region ?? previous.filters.region ?? "") === region
    ? previous : null;
  const dimensions = data?.option_dimensions || scopedPrevious?.option_dimensions;
  const derived = useMemo(
    () => resolveProductFilterDimensions(dimensions, id, region, requested),
    [dimensions, id, region, requested],
  );
  const meta = data || scopedPrevious;
  const filters: Filters = data?.filters || derived?.filters || requested;
  const options = data?.options || derived?.options || {
    series: [], presentations: [], units: [], markets: [],
  };
  // Share/bookmark/report links describe the visible selection, including its
  // source-qualified defaults while a newly requested price is still pending.
  useEffect(() => {
    if (!filtersReady || !preferencesReady) return;
    const current = new URLSearchParams(window.location.search);
    for (const [name, value] of Object.entries({ ...filters, region })) {
      if (value) current.set(name, value);
      else current.delete(name);
    }
    const path = window.location.pathname + (current.size ? `?${current}` : "") + window.location.hash;
    window.history.replaceState(null, "", path);
  }, [data, requested, filtersReady, preferencesReady, region, derived]);
  function filter(name: keyof Filters, value: string) {
    setRequested((old) => ({
      ...old,
      [name]: value,
      ...(name === "series"
        ? { presentation: "", units: "", market: "" }
        : name === "presentation"
          ? { units: "", market: "" }
          : name === "units" && old.market && !marketReportsForUnits(
            dimensions, id, region, filters.series, filters.presentation, value, old.market,
          )
            ? { market: "" }
          : {}),
    }));
  }
  const markets = [...(data?.markets || [])].sort(
    (a, b) => b.price - a.price || b.date.localeCompare(a.date),
  );
  const currentMarkets = markets.filter((m) => m.date === data?.current?.date);
  const unknownOptionLabel = loading || !filtersReady || !preferencesReady
    ? "Opciones pendientes" : "Opciones no disponibles";
  const marketName =
    options.markets.find((m) => m.id === filters.market)?.name ||
    (filters.market
      ? meta ? "Mercado seleccionado" : "Mercado seleccionado · por verificar"
      : "Todos los mercados");
  const priceRegion = filters.market
    ? currentMarkets[0]?.region || region
    : region;
  const city = filters.series === "city";
  const presentationLabel = normalizeLabel(filters.presentation || "", "presentation");
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
                {data?.classification.length
                  ? data.classification
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
              <p className="muted" data-testid="current-product-context">
                {filters.market && currentMarkets.length === 1 ? currentMarkets[0].name : marketName}
                {" · "}{priceRegion || "Colombia"} · COP
              </p>
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
                {presentationLabel} · {filters.units}
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
                ? "Punto medio del rango mínimo–máximo por empaque, usando la última ronda disponible de cada mercado en esa fecha. Para varios mercados, promedio simple de esos puntos medios."
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
                {options.series.map((s) => (
                  <option value={s} key={s}>
                    {priceSeriesLabel[s]}
                  </option>
                ))}
              </select>
            </label>
            <SearchableSelect
              label="Mercado"
              placeholder="Busca un mercado…"
              emptyLabel="Todos los mercados"
              value={filters.market}
              options={quoteMarketOptions(options.markets)}
              onChange={(id) => filter("market", id)}
              loading={loading && !derived && !data}
            />
            <SearchableSelect
              key={filters.series}
              label="Presentación"
              placeholder="Busca una presentación…"
              value={filters.presentation}
              options={quotePresentationOptions(options.presentations)}
              onChange={(id) => filter("presentation", id)}
              loading={loading && !derived && !data}
              allowClear={false}
            />
            <SearchableSelect
              label="Unidades"
              placeholder="Busca unidades…"
              value={filters.units}
              options={options.units.map((v) => ({ id: v, label: v }))}
              onChange={(id) => filter("units", id)}
              loading={loading && !derived && !data}
              allowClear={false}
            />
            <label className="form-field">
              Período del historial
              <select
                aria-label="Período del historial"
                value={filters.history}
                onChange={(e) => filter("history", e.target.value)}
              >
                <option value="recent">Fechas recientes</option>
                <option value="all">Todo el historial</option>
              </select>
            </label>
          </div>
          <p className="field-help" role="note">
            Los mercados disponibles dependen del tipo de precio, la presentación y las unidades elegidas.
            Si no encuentras un mercado, cambia la presentación o las unidades para ver dónde se reporta ese producto.
          </p>
        </>
      )}
      <AppliedFilters
        items={[
          {
            label: "Departamento",
            value: region || "Colombia",
            clear: region ? () => setRegion("") : undefined,
          },
          { label: "Fuente", value: priceSeriesLabel[filters.series] || unknownOptionLabel },
          { label: "Mercado", value: marketName },
          { label: "Presentación", value: presentationLabel || unknownOptionLabel },
          { label: "Unidades", value: filters.units || unknownOptionLabel },
          { label: "Moneda", value: "COP · pesos colombianos" },
          {
            label: "Período",
            value: filters.history === "all" ? "Todo el historial" : "Fechas recientes",
          },
        ]}
      />
      {meta && <DetailTabs mode={mode} onChange={setMode} />}
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
                  unit={`COP / ${presentationLabel} · ${filters.units}`}
                  evidenceContext={{ product: id, productName: data.product.name,
                    department: priceRegion, presentation: filters.presentation, units: filters.units, currency: "COP" }}
                />
                <p className="privacy-note">
                  La gráfica y los mercados usan los filtros mostrados arriba.
                  La cobertura de mercados puede cambiar entre fechas.
                </p>
                <MarketList markets={markets} productName={data.product.name} />
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
                      product={id}
                      productName={data.product.name}
                      department={currentMarkets[0].region || region}
                      market={currentMarkets[0].id}
                      marketName={currentMarkets[0].name}
                      presentation={filters.presentation}
                      units={currentMarkets[0].source_units || filters.units}
                      currency="COP"
                      month={data.current?.date}
                    >
                      {currentMarkets.length > 1
                        ? "Consultar una de las fuentes del promedio"
                        : "Consultar fuente del precio actual"}
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
