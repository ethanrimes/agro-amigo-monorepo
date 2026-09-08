"use client";
import { useState } from "react";
import {
  IoBarChartOutline,
  IoGridOutline,
  IoDownloadOutline,
} from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { SearchBox } from "@/components/ui/SearchBox";
import { SeasonalChart } from "@/components/planning/SeasonalChart";
import { ErrorState } from "@/components/marketplace/Shared";
import type {
  CropReference,
  FarmData,
  CostTemplate,
  Seasonality,
  Evidence,
} from "@/lib/planning-types";
import type { Catalog, MarketPrice, Coffee } from "@/lib/market-types";
import { number, money, dateLabel } from "@/lib/market-types";
import { FULL_MONTHS } from "@/lib/location-types";
import { fold, seasonalPrices } from "@/lib/planning-math";
import {
  cleanResult,
  waterfallRows,
  comparableProduct,
  type CleanInputs,
  type CleanCost,
} from "@/lib/cleansheet";
const initialCosts: CleanCost[] = [
  { label: "Labores antes de cosecha", amount: "", timing: "before" },
  { label: "Semilla e insumos", amount: "", timing: "before" },
  { label: "Mano de obra de cosecha", amount: "", timing: "harvest" },
  { label: "Otros rubros del total publicado", amount: "", timing: "before" },
];
function Waterfall({ inputs }: { inputs: CleanInputs }) {
  const rows = waterfallRows(inputs);
  const min = Math.min(0, ...rows.flatMap((r) => [r.start, r.end]));
  const max = Math.max(1, ...rows.flatMap((r) => [r.start, r.end]));
  const x = (v: number) => ((v - min) / (max - min)) * 100;
  return (
    <figure
      className="clean-waterfall"
      aria-label="Cascada: de los ingresos a la utilidad después de cada costo"
    >
      {rows.map((r, i) => (
        <div className="waterfall-row" key={i}>
          <span className="waterfall-row-label">{r.label}</span>
          <div className="waterfall-track" aria-hidden="true">
            <i className="waterfall-zero" style={{ left: x(0) + "%" }} />
            <span
              className="waterfall-bar"
              style={{
                left: x(Math.min(r.start, r.end)) + "%",
                width: Math.abs(x(r.end) - x(r.start)) + "%",
                background:
                  r.kind === "revenue"
                    ? "#285d82"
                    : r.kind === "profit"
                      ? r.value >= 0
                        ? "#246345"
                        : "#ac3f33"
                      : "#d49a4b",
              }}
            />
            {i < rows.length - 2 && (
              <i
                className="waterfall-connector"
                style={{ left: x(r.end) + "%" }}
              />
            )}
          </div>
          <strong className="waterfall-row-value">{money(r.value)}</strong>
        </div>
      ))}
      <figcaption>
        Valores totales en pesos colombianos (COP). Cada costo reduce el saldo
        hasta la utilidad o pérdida.
      </figcaption>
    </figure>
  );
}
function BenchmarkCoffee({ cost }: { cost: number | null }) {
  const ref = useData<Evidence>("/api/evidence/coffee-cost-benchmark");
  const benchmark = Number(ref.data?.metadata.cost_per_125kg) / 125;
  if (!ref.data || !Number.isFinite(benchmark)) return null;
  return (
    <div className="clean-benchmark-note">
      <b>Café: referencia nacional FEPCafé</b>
      <p>
        {money(benchmark)}/kg de pergamino seco · febrero de 2026.
        {cost !== null && (
          <>
            {" "}
            Tu costo de producción por kg vendible:{" "}
            <strong>{money(cost)}</strong>. Diferencia nominal:{" "}
            {number((cost / benchmark - 1) * 100)}%.
          </>
        )}
      </p>
      <p>
        Promedio nacional, no pares de tu municipio. Compara el mismo estado del
        café y alcance de costos; tu rendimiento y los rubros incluidos pueden
        ser distintos.
      </p>
      <EvidenceLink id={ref.data.id} page={6}>
        Ver costo publicado y componentes
      </EvidenceLink>
      <EvidenceLink id={ref.data.id} page={10}>
        Método de FEPCafé
      </EvidenceLink>
    </div>
  );
}
function CropSheet({ crop, data }: { crop: CropReference; data: FarmData }) {
  const coffee = fold(crop.crop) === "cafe",
    permanent = crop.cycle === "Permanente";
  const templates = data.templates
    .filter((t) => fold(t.crop) === fold(crop.crop))
    .sort(
      (a, b) =>
        Number(b.municipalities.includes(data.municipality.id)) -
        Number(a.municipalities.includes(data.municipality.id)),
    );
  const [area, setArea] = useState("1"),
    [yieldKg, setYield] = useState(
      crop.yield_kg_ha ? String(Math.round(crop.yield_kg_ha)) : "",
    ),
    [loss, setLoss] = useState("0"),
    [delivery, setDelivery] = useState("0"),
    [commission, setCommission] = useState("0"),
    [costs, setCosts] = useState(initialCosts.map((c) => ({ ...c }))),
    [templateId, setTemplate] = useState(templates[0]?.id || ""),
    [comparable, setComparable] = useState(false),
    [costOrigin, setCostOrigin] = useState(""),
    [view, setView] = useState("waterfall"),
    [mode, setMode] = useState("history"),
    [manualPrice, setManualPrice] = useState(""),
    [discount, setDiscount] = useState("0"),
    [productId, setProduct] = useState(""),
    [marketId, setMarket] = useState(""),
    [month, setMonth] = useState(new Date().getMonth() + 1),
    [priceConfirmed, setPriceConfirmed] = useState(false),
    [uncertainty, setUncertainty] = useState("20"),
    [message, setMessage] = useState("");
  const catalog = useData<Catalog>("/api/catalog"),
    products =
      catalog.data?.products.filter((p) =>
        comparableProduct(crop.crop, p.name),
      ) || [];
  const product = coffee
    ? "cafe-pergamino-seco"
    : products.find((p) => p.id === productId)?.id ||
      products.find(
        (p) =>
          fold(crop.variety).includes("hass") && fold(p.name).includes("hass"),
      )?.id ||
      products[0]?.id ||
      "";
  const detail = useData<{ markets: MarketPrice[] }>(
      !coffee && product ? "/api/products/" + product : null,
    ),
    markets = [...(detail.data?.markets || [])].sort(
      (a, b) =>
        Number(fold(b.region) === fold(data.municipality.department)) -
        Number(fold(a.region) === fold(data.municipality.department)),
    );
  const market = coffee
    ? "fnc-national"
    : markets.find((m) => m.id === marketId)?.id || markets[0]?.id || "";
  const history = useData<Seasonality>(
    product && market
      ? `/api/planning/seasonality?product=${encodeURIComponent(product)}&market=${encodeURIComponent(market)}`
      : null,
  );
  const coffeeData = useData<Coffee>(coffee ? "/api/coffee" : null);
  const latestDocument = coffee
    ? coffeeData.data?.document_id
    : markets.find((m) => m.id === market)?.document_id;
  const historyUnitValid =
    history.data && ["kg", "kg de pergamino seco"].includes(history.data.unit);
  const projected =
    history.data && historyUnitValid
      ? seasonalPrices(history.data, month)
      : null;
  const discountValid =
    discount.trim() !== "" &&
    Number.isFinite(+discount) &&
    +discount >= 0 &&
    +discount < 100;
  const price =
    mode === "manual"
      ? manualPrice
      : projected && priceConfirmed && discountValid
        ? String(projected.typical * (1 - +discount / 100))
        : "";
  const inputs: CleanInputs = {
    area,
    yieldKg,
    loss,
    delivery,
    commission,
    costs,
    price,
  };
  const result = cleanResult(inputs),
    template = templates.find((t) => t.id === templateId);
  const usableBenchmark = comparable ? template : undefined;
  const validUncertainty =
    uncertainty.trim() !== "" &&
    Number.isFinite(+uncertainty) &&
    +uncertainty >= 0 &&
    +uncertainty < 100;
  const ranges =
    result && validUncertainty
      ? ([-1, 0, 1] as const).map((delta, i) => {
          const p =
            mode === "history" && projected
              ? [projected.low, projected.typical, projected.high][i] *
                (1 - +discount / 100)
              : +price;
          return cleanResult({
            ...inputs,
            yieldKg: String(+yieldKg * (1 + (delta * +uncertainty) / 100)),
            price: String(p),
          });
        })
      : null;
  const applyTemplate = (t: CostTemplate) => {
    setCosts(t.costs.map((c) => ({ ...c, amount: String(c.amount) })));
    setCostOrigin(t.id);
    setMessage(
      "Cargamos los costos nominales del estudio. Ajusta cada rubro a tus condiciones y al año de tu escenario.",
    );
  };
  const exportScenario = () => {
    if (!result) return;
    const raw = JSON.stringify(
      {
        format: "agroamigo-cleansheet",
        version: 1,
        createdAt: new Date().toISOString(),
        municipality: data.municipality.id,
        crop: crop.variety,
        physicalState: crop.physical_state,
        period: permanent ? "Un año en producción" : "Un ciclo productivo",
        inputs,
        result,
        sensitivity: ranges,
        assumptions: {
          priceMode: mode,
          month,
          product,
          market,
          discount,
          uncertainty,
          costOrigin,
          benchmarkComparable: comparable,
        },
        sources: {
          yield: crop.document_id,
          cost: templates.find((t) => t.id === costOrigin)?.document_id,
          benchmark: template?.document_id,
          latestPrice: mode === "history" ? latestDocument : undefined,
          history: history.data?.years.map((y) => y.document_id),
        },
      },
      null,
      2,
    );
    if (/AgroAmigo(Android|IOS)\//.test(navigator.userAgent)) {
      window.location.href =
        "agroamigo-export://scenario?data=" + encodeURIComponent(raw);
      return;
    }
    const url = URL.createObjectURL(
        new Blob([raw], { type: "application/json" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = "analisis-agroamigo.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="clean-sheet">
      <div className="clean-period">
        <span>
          {permanent ? "Un año en producción" : "Un ciclo productivo"}
        </span>
        <span>{crop.physical_state}</span>
        <span>COP · pesos colombianos</span>
      </div>
      <div className="clean-input-sections">
        <section className="panel clean-assumptions">
          <span className="eyebrow">1 · COSECHA ESPERADA</span>
          <h3>¿Cuánto podrías vender?</h3>
          <div className="clean-fields">
            <label>
              Área que quieres analizar (ha)
              <input
                type="number"
                inputMode="decimal"
                min="0.01"
                step="any"
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </label>
            <label>
              Rendimiento esperado (kg/ha)
              <input
                type="number"
                inputMode="decimal"
                min="1"
                value={yieldKg}
                onChange={(e) => setYield(e.target.value)}
              />
            </label>
            <label>
              Pérdidas antes de vender (%)
              <input
                type="number"
                inputMode="decimal"
                min="0"
                max="99"
                value={loss}
                onChange={(e) => setLoss(e.target.value)}
              />
            </label>
          </div>
          <p>
            Referencia municipal EVA {crop.reference_year}:{" "}
            <b>
              {crop.yield_kg_ha
                ? number(crop.yield_kg_ha) + " kg/ha"
                : "sin rendimiento publicado"}
            </b>{" "}
            de {crop.variety.toLowerCase()}. Es una referencia territorial, no
            un rendimiento garantizado.
          </p>
          <EvidenceLink
            id={crop.document_id}
            municipality={data.municipality.id}
          >
            Ver producción, área cosechada y rendimiento
          </EvidenceLink>
          {crop.yield_kg_ha && yieldKg.trim() !== "" && +yieldKg > 0 && (
            <p className="clean-delta">
              Tu supuesto: {number((+yieldKg / crop.yield_kg_ha - 1) * 100)}%
              frente al rendimiento municipal, para el período y estado
              indicados.
            </p>
          )}
        </section>
        <section className="panel clean-assumptions">
          <span className="eyebrow">2 · PRECIO DE VENTA</span>
          <h3>¿A qué precio harías las cuentas?</h3>
          <div
            className="segment-control"
            role="group"
            aria-label="Origen del precio"
          >
            <button
              aria-pressed={mode === "history"}
              className={mode === "history" ? "active" : ""}
              onClick={() => setMode("history")}
            >
              Referencia histórica
            </button>
            <button
              aria-pressed={mode === "manual"}
              className={mode === "manual" ? "active" : ""}
              onClick={() => setMode("manual")}
            >
              Mi precio
            </button>
          </div>
          {mode === "manual" ? (
            <label className="clean-single-field">
              Mi precio esperado (COP/kg)
              <input
                type="number"
                inputMode="decimal"
                min="1"
                value={manualPrice}
                onChange={(e) => setManualPrice(e.target.value)}
              />
              <small>
                Supuesto propio para {crop.physical_state.toLowerCase()}. No se
                publica como una oferta.
              </small>
            </label>
          ) : (
            <>
              <div className="clean-fields">
                {!coffee && (
                  <>
                    <label>
                      Producto comparable
                      <select
                        value={product}
                        onChange={(e) => {
                          setProduct(e.target.value);
                          setMarket("");
                          setPriceConfirmed(false);
                        }}
                      >
                        <option value="">Sin selección</option>
                        {products.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Mercado de referencia
                      <select
                        value={market}
                        onChange={(e) => {
                          setMarket(e.target.value);
                          setPriceConfirmed(false);
                        }}
                      >
                        <option value="">Sin mercado</option>
                        {markets.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
                <label>
                  Mes de venta del escenario
                  <select
                    value={month}
                    onChange={(e) => setMonth(+e.target.value)}
                  >
                    {FULL_MONTHS.map((m, i) => (
                      <option key={m} value={i + 1}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Ajuste de la referencia a mi venta (%)
                  <input
                    type="number"
                    min="0"
                    max="99"
                    inputMode="decimal"
                    value={discount}
                    onChange={(e) => setDiscount(e.target.value)}
                  />
                </label>
              </div>
              {history.loading && product && market ? (
                <p role="status">Revisando años completos de precios…</p>
              ) : history.error ? (
                <ErrorState message={history.error} retry={history.retry} />
              ) : projected ? (
                <>
                  <p className="clean-price">
                    <b>{money(projected.typical)}/kg</b>
                    <span>
                      Referencia estacional · {projected.samples} años completos
                    </span>
                  </p>
                  <p>
                    {coffee
                      ? "Referencia nacional FNC de pergamino seco."
                      : "Precio mayorista SIPSA, antes de ajustar a tu venta."}{" "}
                    Última base:{" "}
                    {history.data?.latest
                      ? dateLabel(history.data.latest.date)
                      : "sin fecha"}
                    . El ajuste es un descuento propio; ingresa transporte
                    aparte.
                  </p>
                  <label className="clean-check">
                    <input
                      type="checkbox"
                      checked={priceConfirmed}
                      onChange={(e) => setPriceConfirmed(e.target.checked)}
                    />
                    Confirmo que mi cosecha se venderá en el mismo estado y
                    unidad de este precio; revisé el ajuste.
                  </label>
                </>
              ) : (
                <p className="inline-note">
                  No hay una serie comparable con al menos tres años completos
                  para esta selección. Usa «Mi precio» para calcular sin
                  inventar una tendencia.
                </p>
              )}
            </>
          )}
        </section>
      </div>
      <section className="panel clean-cost-panel">
        <span className="eyebrow">3 · COSTOS DESDE CERO</span>
        <h3>¿En qué se iría el dinero?</h3>
        <p>
          Escribe los costos por hectárea del mismo{" "}
          {permanent ? "año en producción" : "ciclo"}. Incluye el valor de tu
          trabajo, uso de tierra, equipos y financiación cuando correspondan.
        </p>
        {templates.length > 0 ? (
          <div className="clean-template">
            <label>
              Estudio de costos para comparar
              <select
                value={templateId}
                onChange={(e) => {
                  setTemplate(e.target.value);
                  setComparable(false);
                }}
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.region} · {t.reference_year}
                  </option>
                ))}
              </select>
            </label>
            {template && (
              <>
                <p>
                  {template.production_system}. Rendimiento del estudio:{" "}
                  {number(template.yield_kg_ha)} kg/ha.{" "}
                  <b>
                    Pesos nominales de {template.reference_year}, sin
                    actualización automática.
                  </b>
                </p>
                <EvidenceLink
                  id={template.document_id}
                  page={template.source_page}
                >
                  Ver tabla original UPRA · página {template.source_page}
                </EvidenceLink>
                <label className="clean-check">
                  <input
                    type="checkbox"
                    checked={comparable}
                    onChange={(e) => setComparable(e.target.checked)}
                  />
                  El sistema, período y alcance de costos del estudio sirven
                  para comparar mi escenario. Entiendo la diferencia de año y
                  región.
                </label>
                <button
                  className="button secondary"
                  onClick={() => applyTemplate(template)}
                >
                  Usar costos del estudio como punto de partida
                </button>
              </>
            )}
          </div>
        ) : (
          <p className="inline-note">
            No tenemos una estructura regional de costos validada para este
            cultivo. Completa los rubros con tus estimaciones; no los tratamos
            como cero.
          </p>
        )}
        <div className="clean-cost-edit">
          {costs.map((c, i) => {
            const ref = usableBenchmark?.costs.find((r) => r.label === c.label);
            const value =
              c.amount.trim() !== "" &&
              Number.isFinite(+c.amount) &&
              +c.amount >= 0
                ? +c.amount
                : null;
            return (
              <div className="clean-cost-line" key={i}>
                <label>
                  {c.label}
                  <span className="cost-input">
                    <span>$</span>
                    <input
                      aria-label={c.label + " (COP/ha)"}
                      type="number"
                      inputMode="decimal"
                      min="0"
                      value={c.amount}
                      placeholder="Por completar"
                      onChange={(e) =>
                        setCosts(
                          costs.map((r, j) =>
                            i === j ? { ...r, amount: e.target.value } : r,
                          ),
                        )
                      }
                    />
                    <small>/ha</small>
                  </span>
                </label>
                <div className="clean-comparison">
                  {ref ? (
                    <>
                      <span>
                        UPRA {template?.reference_year}: {money(ref.amount)}/ha
                      </span>
                      {value !== null && (
                        <strong>
                          {value >= ref.amount ? "+" : ""}
                          {money(value - ref.amount)}
                          {ref.amount > 0
                            ? ` (${number((value / ref.amount - 1) * 100)}%)`
                            : ""}{" "}
                          nominal
                        </strong>
                      )}
                    </>
                  ) : (
                    <span>
                      {comparable
                        ? "Sin rubro equivalente"
                        : "Activa la comparación para ver diferencias"}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {message && (
          <p role="status" className="inline-note">
            {message}
          </p>
        )}
        <div className="clean-fields clean-sale-costs">
          <label>
            Transporte, empaque y venta (COP totales)
            <input
              type="number"
              inputMode="decimal"
              min="0"
              value={delivery}
              onChange={(e) => setDelivery(e.target.value)}
            />
          </label>
          <label>
            Comisión sobre la venta (%)
            <input
              type="number"
              inputMode="decimal"
              min="0"
              max="99"
              value={commission}
              onChange={(e) => setCommission(e.target.value)}
            />
          </label>
        </div>
        <p className="field-help">
          Escribe 0 solo si el rubro no aplica o ya está incluido; evita contar
          transporte o comisiones dos veces. Una diferencia nominal con UPRA no
          mide eficiencia ni te ubica en un percentil de agricultores.
        </p>
      </section>
      <section className="clean-results panel">
        <div className="clean-result-heading">
          <div>
            <span className="eyebrow">EL RESULTADO DE TUS SUPUESTOS</span>
            <h3>De la cosecha a lo que te queda</h3>
          </div>
          <div
            className="segment-control"
            role="group"
            aria-label="Presentación del análisis"
          >
            <button
              className={view === "waterfall" ? "active" : ""}
              aria-pressed={view === "waterfall"}
              onClick={() => setView("waterfall")}
            >
              <IoBarChartOutline />
              Cascada
            </button>
            <button
              className={view === "table" ? "active" : ""}
              aria-pressed={view === "table"}
              onClick={() => setView("table")}
            >
              <IoGridOutline />
              Tabla
            </button>
          </div>
        </div>
        {result ? (
          <>
            <div className="clean-kpis">
              <div>
                <span>Ingresos estimados</span>
                <strong>{money(result.revenue)}</strong>
                <small>{number(result.quantity)} kg vendibles</small>
              </div>
              <div>
                <span>Costos y venta</span>
                <strong>{money(result.total)}</strong>
                <small>Incluye comisión y transporte</small>
              </div>
              <div className={result.profit >= 0 ? "profit" : "loss"}>
                <span>
                  {result.profit >= 0
                    ? "Utilidad estimada"
                    : "Pérdida estimada"}
                </span>
                <strong>{money(result.profit)}</strong>
                <small>Margen: {number(result.margin)}%</small>
              </div>
              <div>
                <span>Precio de equilibrio</span>
                <strong>{money(result.breakEven)}/kg</strong>
                <small>Para cubrir todos los costos ingresados</small>
              </div>
            </div>
            {view === "waterfall" ? (
              <Waterfall inputs={inputs} />
            ) : (
              <div className="clean-table-wrap">
                <table className="clean-result-table">
                  <caption>
                    {crop.variety} · {area} ha ·{" "}
                    {permanent ? "un año en producción" : "un ciclo"}
                  </caption>
                  <thead>
                    <tr>
                      <th>Concepto</th>
                      <th>Por hectárea</th>
                      <th>Total del escenario</th>
                      <th>Referencia UPRA / ha</th>
                      <th>Diferencia nominal / ha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {waterfallRows(inputs).map((r, i) => {
                      const ref = usableBenchmark?.costs.find(
                        (c) => c.label === r.label,
                      );
                      return (
                        <tr
                          key={i}
                          className={r.kind === "profit" ? "total" : ""}
                        >
                          <th scope="row">{r.label}</th>
                          <td>{money(r.value / +area)}</td>
                          <td>{money(r.value)}</td>
                          <td>{ref ? money(ref.amount) : "No comparable"}</td>
                          <td>
                            {ref ? money(-r.value / +area - ref.amount) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="clean-equation">
              <b>Precio de equilibrio</b>
              <span>
                (Costos de producción + transporte y venta) ÷ (kilos vendibles ×
                (1 − comisión))
              </span>
            </div>
            <p>
              Costos antes de cosecha: <b>{money(result.before)}</b>, según la
              clasificación de estos rubros. El resultado incluye solamente los
              costos que ingresaste; no estima impuestos ni costos omitidos.
            </p>
            <div className="clean-sensitivity">
              <label>
                Variación del rendimiento para explorar (%)
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  max="99"
                  value={uncertainty}
                  onChange={(e) => setUncertainty(e.target.value)}
                />
              </label>
              {ranges && (
                <div className="clean-range-cards">
                  {ranges.map((r, i) => (
                    <div key={i}>
                      <span>
                        {
                          [
                            "Escenario bajo",
                            "Escenario central",
                            "Escenario alto",
                          ][i]
                        }
                      </span>
                      <b>{r ? money(r.profit) : "—"}</b>
                      <small>Utilidad estimada</small>
                    </div>
                  ))}
                </div>
              )}
              <p>
                Estos escenarios combinan rendimiento ±{uncertainty}% con{" "}
                {mode === "history"
                  ? "los cuartiles históricos del precio ajustado"
                  : "el precio que ingresaste"}
                . Mantienen los costos fijos para explorar sensibilidad; no son
                probabilidades ni una promesa de ingreso.
              </p>
            </div>
            <button className="button secondary" onClick={exportScenario}>
              <IoDownloadOutline />
              Descargar análisis con sus fuentes
            </button>
          </>
        ) : (
          <div className="clean-incomplete">
            <IoBarChartOutline />
            <h4>Completa los supuestos para ver el resultado</h4>
            <p>
              Necesitamos área y rendimiento positivos, precio, pérdidas y
              comisiones menores al 100%, y todos los costos. Los campos vacíos
              no se convierten en cero.
            </p>
          </div>
        )}
      </section>
      {coffee && <BenchmarkCoffee cost={result?.costPerKg ?? null} />}
      <details className="clean-method">
        <summary>
          De dónde salen los datos y qué permite comparar el censo
        </summary>
        <p>
          EVA aporta producción y rendimiento municipal. Las estructuras UPRA
          son estudios técnicos regionales con rubros comparables, no un ranking
          de fincas vecinas. El Censo Nacional Agropecuario 2014 de DANE no
          recoge costos de producción, precios de venta ni ingresos.
        </p>
        <a
          href="https://microdatos.dane.gov.co/index.php/catalog/513"
          target="_blank"
          rel="noreferrer"
        >
          DANE · alcance y metodología del CNA 2014 ↗
        </a>
        <p>
          EMICRON 2024 sí incluye gastos de actividades agrícolas, pecuarias y
          extractivas, pero ese rubro agrupa insumos y actividades diferentes;
          no lo usamos como costo de este cultivo por hectárea.
        </p>
        <a
          href="https://microdatos.dane.gov.co/index.php/catalog/875/variable/F8/V147?name=P3057_D"
          target="_blank"
          rel="noreferrer"
        >
          DANE · variable de costos de EMICRON 2024 ↗
        </a>
        {history.data && (
          <>
            <p>
              Estacionalidad: por cada año completo dividimos el precio del mes
              elegido por el del mes de la última observación; multiplicamos la
              mediana de esos cocientes por el último precio. Se requieren al
              menos tres años completos. No ajusta inflación, calidad ni choques
              futuros de mercado.
            </p>
            <div className="clean-history-sources">
              {latestDocument && (
                <EvidenceLink id={latestDocument}>
                  Último precio usado como base
                </EvidenceLink>
              )}
              {history.data.years.map((y) => (
                <EvidenceLink key={y.reference_year} id={y.document_id}>
                  Precios {y.reference_year} · libro original
                </EvidenceLink>
              ))}
            </div>
            <SeasonalChart
              data={history.data}
              month={month}
              onMonth={setMonth}
            />
          </>
        )}
      </details>
    </div>
  );
}
export function CleanSheet({
  data,
  initialCrop = "",
}: {
  data: FarmData;
  initialCrop?: string;
}) {
  const [id, setId] = useState(initialCrop),
    [query, setQuery] = useState("");
  const crop =
    data.crops.find((c) => c.crop_code === id) ||
    data.crops.find((c) => fold(c.crop) === "cafe") ||
    data.crops[0];
  return (
    <div className="clean-workspace">
      <div className="zone-intro">
        <div>
          <span className="eyebrow">COSTOS Y RENTABILIDAD</span>
          <h2>Explora una idea antes de invertir.</h2>
          <p>
            Combina referencias públicas con tus supuestos. Cada cifra tiene un
            origen.
          </p>
        </div>
      </div>
      <div className="panel clean-crop-selector">
        <label>Cultivo para el análisis</label>
        <SearchBox
          label="Elegir cultivo para el análisis"
          value={query}
          onChange={setQuery}
          options={data.crops.map((c) => ({
            id: c.crop_code,
            label: c.variety,
            detail: c.crop + " · " + c.physical_state,
          }))}
          onSelect={(o) => setId(o.id)}
        />
        {crop && (
          <p>
            <strong>{crop.variety}</strong> · Referencias de{" "}
            {data.municipality.name}, {data.municipality.department}
          </p>
        )}
      </div>
      {crop ? (
        <CropSheet
          key={data.municipality.id + "-" + crop.crop_code}
          crop={crop}
          data={data}
        />
      ) : (
        <p className="inline-note">
          No hay cultivos con referencia EVA para este municipio.
        </p>
      )}
    </div>
  );
}
