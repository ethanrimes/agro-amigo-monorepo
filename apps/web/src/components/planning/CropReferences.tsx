"use client";
import { useState } from "react";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { money, number } from "@/lib/market-types";
import type { MarketPrice } from "@/lib/market-types";
import type { UnifiedCatalog } from "@/lib/catalog-types";
import type {
  CropReference,
  FarmData,
  Seasonality,
} from "@/lib/planning-types";
import { comparableProduct } from "@/lib/cleansheet";
import { fold, MONTHS } from "@/lib/planning-math";
import { EvidenceLink } from "./EvidenceLink";
import { CoffeeCostReference } from "./CoffeeCostReference";
import { SeasonalChart } from "./SeasonalChart";
import styles from "./CropReferences.module.css";

function HistoricalPrices({ crop }: { crop: CropReference }) {
  const coffee = fold(crop.crop) === "cafe";
  const [selectedProduct, setProduct] = useState("");
  const [selectedMarket, setMarket] = useState("");
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const catalog = useData<UnifiedCatalog>(
    coffee ? null : "/api/catalog?view=canonical",
  );
  const products =
    catalog.data?.products.filter(
      (p) =>
        p.kind === "product" &&
        p.currency === "COP" &&
        p.unit === "kg" &&
        p.series === "monthly" &&
        comparableProduct(crop.crop, p.name),
    ) || [];
  const product = coffee
    ? "cafe-pergamino-seco"
    : products.find((p) => p.id === selectedProduct)?.id ||
      products.find(
        (p) =>
          fold(crop.variety).includes("hass") && fold(p.name).includes("hass"),
      )?.id ||
      products[0]?.id ||
      "";
  const detail = useData<{ markets: MarketPrice[] }>(
    !coffee && product
      ? `/api/products/${encodeURIComponent(product)}?region=&series=monthly&presentation=Por+unidad+de+medida&units=1+kg`
      : null,
  );
  const markets = detail.data?.markets.filter((m) => m.unit === "kg") || [];
  const market = coffee
    ? "fnc-national"
    : markets.find((m) => m.id === selectedMarket)?.id || markets[0]?.id || "";
  const history = useData<Seasonality>(
    product && market
      ? `/api/planning/seasonality?product=${encodeURIComponent(product)}&market=${encodeURIComponent(market)}`
      : null,
  );
  const validUnit =
    history.data?.unit === (coffee ? "kg de pergamino seco" : "kg");
  return (
    <section className="crop-history-references">
      {!coffee && (
        <div className="form-grid">
          <label className="form-field">
            Producto comparable
            <select
              value={product}
              onChange={(e) => {
                setProduct(e.target.value);
                setMarket("");
              }}
            >
              {!products.length && (
                <option value="">Sin referencia comparable</option>
              )}
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Mercado de referencia
            <select value={market} onChange={(e) => setMarket(e.target.value)}>
              {!markets.length && (
                <option value="">Sin mercado disponible</option>
              )}
              {markets.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <p className="privacy-note">
        {coffee
          ? "FNC · café pergamino seco · COP/kg, convertido desde la carga de 125 kg."
          : "DANE SIPSA · promedio mensual mayorista · COP/kg del producto y mercado seleccionados."}{" "}
        Son referencias históricas, no precios futuros ni ingresos de tu finca.
      </p>
      {catalog.loading || detail.loading || history.loading ? (
        <p role="status">Consultando precios históricos…</p>
      ) : null}
      {catalog.error && (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      )}
      {detail.error && (
        <ErrorState message={detail.error} retry={detail.retry} />
      )}
      {history.error && (
        <ErrorState message={history.error} retry={history.retry} />
      )}
      {!coffee && !catalog.loading && !catalog.error && !product && (
        <p>
          No hay un producto mensual en COP/kg que corresponda a este cultivo y
          estado. No se sustituye por otro producto o unidad.
        </p>
      )}
      {history.data && !validUnit && (
        <p role="alert">
          La referencia disponible no corresponde al precio por kg de este
          producto. No se mezcla con esta consulta.
        </p>
      )}
      {history.data && validUnit && (
        <SeasonalChart data={history.data} month={month} onMonth={setMonth} />
      )}
      {product && (
        <Link
          className="button secondary"
          href={
            coffee
              ? "/coffee"
              : `/product/${encodeURIComponent(product)}?region=&series=monthly&presentation=Por+unidad+de+medida&units=1+kg&market=${encodeURIComponent(market)}&history=all`
          }
        >
          Consultar precios y fuentes del producto →
        </Link>
      )}
    </section>
  );
}

/** Public references only. Reading this component never writes farm or scenario state. */
export function CropReferences({
  crop,
  data,
}: {
  crop: CropReference;
  data: FarmData;
}) {
  const coffee = fold(crop.crop) === "cafe";
  const calendars = data.calendars.filter(
    (c) => fold(c.crop) === fold(crop.crop),
  );
  const templates = data.templates.filter(
    (t) => fold(t.crop) === fold(crop.crop),
  );
  const [showHistory, setShowHistory] = useState(false);
  return (
    <div
      className={"crop-references " + styles.references}
      id="crop-references"
    >
      <section className="panel">
        <span className="eyebrow">
          {data.municipality.name}, {data.municipality.department} · EVA{" "}
          {crop.reference_year}
        </span>
        <h2>{crop.variety}</h2>
        <p>
          {crop.physical_state} · {crop.cycle}. Rendimiento municipal:{" "}
          {crop.yield_kg_ha == null
            ? "sin dato"
            : `${number(crop.yield_kg_ha)} kg/ha`}
          . Producción reportada: {number(crop.production_t)} toneladas; área
          cosechada: {number(crop.harvested_ha)} ha.
        </p>
        <p className="privacy-note">
          Referencia del municipio y año publicados; no es una medición de tu
          finca ni un rendimiento garantizado.
        </p>
        <EvidenceLink id={crop.document_id} municipality={data.municipality.id}>
          Ver producción y cálculo del rendimiento
        </EvidenceLink>
      </section>
      <section className="panel harvest-panel">
        <h2>Calendario histórico del cultivo</h2>
        {calendars.length ? (
          <>
            <p>
              Distribución del área de {crop.crop} en{" "}
              {data.municipality.department}. Cada fila conserva su actividad y
              año; no indica la fecha óptima de siembra de este año.
            </p>
            <div className="calendar-scroll">
              <table className="data-table calendar-table">
                <caption>Área reportada (%) por mes</caption>
                <thead>
                  <tr>
                    <th>Actividad · año</th>
                    {MONTHS.map((m) => (
                      <th key={m}>{m}</th>
                    ))}
                    <th>Fuente</th>
                  </tr>
                </thead>
                <tbody>
                  {calendars.map((c, i) => (
                    <tr key={`${c.document_id}-${c.source_row}-${i}`}>
                      <th>
                        {c.activity} · {c.reference_year}
                      </th>
                      {c.percentages.map((v, month) => (
                        <td key={month}>{number(v)}</td>
                      ))}
                      <td>
                        <EvidenceLink
                          id={c.document_id}
                          department={data.municipality.department_id}
                        >
                          Comprobar calendario de UPRA
                        </EvidenceLink>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p>
            No hay calendario departamental integrado para este cultivo. No
            inferimos una temporada a partir de otros cultivos.
          </p>
        )}
        {coffee && (
          <div className="inline-note">
            <h3>Desarrollo del café desde la floración</h3>
            <p>
              Cenicafé describe diferencias de 28 a 36 semanas según altitud. Es
              una referencia de desarrollo; no una fecha calculada para tu
              finca. Confirma la madurez en el cultivo.
            </p>
            <EvidenceLink id="coffee-development" page={2}>
              Consultar estudio de Cenicafé
            </EvidenceLink>
          </div>
        )}
      </section>
      <section className="panel published-cost-references">
        <h2>Estudios publicados de costos</h2>
        <p>
          Valores nominales del año, región y sistema de cada estudio. No son
          costos actuales ni un presupuesto de tu finca.
        </p>
        {templates.length ? (
          templates.map((t) => (
            <details className="source-explanation" key={t.id}>
              <summary>
                {t.title} · {t.reference_year}
              </summary>
              <p>
                {t.region} · {t.production_system} · rendimiento del estudio:{" "}
                {number(t.yield_kg_ha)} kg/ha.
              </p>
              <p>
                {t.municipalities.includes(data.municipality.id)
                  ? "El estudio incluye este municipio."
                  : "El estudio no identifica este municipio; consulta su alcance regional."}
              </p>
              <p>
                {t.notes.replace(
                  "La asignación del momento de pago es editable; no proviene de un calendario financiero de UPRA.",
                  "El estudio no se presenta como un calendario de pagos.",
                )}
              </p>
              <div className="table-scroll">
                <table className="data-table">
                  <caption>Rubros publicados en COP por hectárea</caption>
                  <thead>
                    <tr>
                      <th>Rubro</th>
                      <th>COP/ha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.costs.map((c, i) => (
                      <tr key={i}>
                        <th>{c.label}</th>
                        <td>{money(c.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th>Total de los rubros publicados</th>
                      <td>
                        {money(t.costs.reduce((sum, c) => sum + c.amount, 0))}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              <EvidenceLink id={t.document_id} page={t.source_page}>
                Ver tabla original de costos · página {t.source_page}
              </EvidenceLink>
            </details>
          ))
        ) : (
          <p>
            No hay un estudio de costos integrado para este cultivo. No se le
            asignan costos de otro sistema.
          </p>
        )}
        {coffee && <CoffeeCostReference />}
      </section>
      <details
        className="panel"
        onToggle={(e) => setShowHistory(e.currentTarget.open)}
      >
        <summary>Consultar historia y estacionalidad de precios</summary>
        {showHistory && <HistoricalPrices crop={crop} />}
      </details>
    </div>
  );
}
