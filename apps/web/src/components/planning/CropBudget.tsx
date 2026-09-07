"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  IoCalculatorOutline,
  IoSaveOutline,
  IoDownloadOutline,
} from "react-icons/io5";
import type {
  CropReference,
  CostTemplate,
  FarmData,
  FarmProfile,
  Seasonality,
} from "@/lib/planning-types";
import type { Catalog, MarketPrice } from "@/lib/market-types";
import { money, number, dateLabel } from "@/lib/market-types";
import {
  fold,
  MONTHS,
  seasonalPrices,
  addDays,
  bogotaToday,
} from "@/lib/planning-math";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EvidenceLink } from "./EvidenceLink";
import { CoffeeCostReference } from "./CoffeeCostReference";
import { SeasonalChart } from "./SeasonalChart";
import type { ManagedCrop, FarmPlan } from "@/lib/farm-types";
type EditCost = { label: string; amount: string; timing: "before" | "harvest" };
const emptyCosts: EditCost[] = [
  { label: "Preparación, siembra y labores", amount: "", timing: "before" },
  { label: "Semilla e insumos", amount: "", timing: "before" },
  { label: "Cosecha y poscosecha", amount: "", timing: "harvest" },
  { label: "Otros costos de producción", amount: "", timing: "before" },
];
export function CropBudget({
  crop,
  data,
  farm,
  managed,
  onApply,
  scenarioKey = "agroamigo-scenarios-v1",
}: {
  crop: CropReference;
  data: FarmData;
  farm: FarmProfile;
  managed?: ManagedCrop;
  onApply?: (p: FarmPlan) => boolean;
  scenarioKey?: string;
}) {
  const seed = managed?.budget;
  const coffee = fold(crop.crop) === "cafe",
    permanent = crop.cycle === "Permanente";
  const [area, setArea] = useState(managed?.area || farm.area || "1"),
    [yieldKg, setYield] = useState(
      managed?.yieldKgHa ||
        (crop.yield_kg_ha ? String(Math.round(crop.yield_kg_ha)) : ""),
    );
  const [period, setPeriod] = useState(
      seed?.periodCode || (permanent ? "annual" : "cycle"),
    ),
    [loss, setLoss] = useState(String(seed?.lossPercent ?? 0)),
    [uncertainty, setUncertainty] = useState(
      String(seed?.uncertaintyPercent ?? 20),
    );
  const [costs, setCosts] = useState<EditCost[]>(
      seed?.costsPerHa.map((c) => ({ ...c, amount: String(c.amount) })) ||
        emptyCosts.map((c) => ({ ...c })),
    ),
    [template, setTemplate] = useState<CostTemplate | null>(
      data.templates.find((t) => t.id === seed?.costSource?.templateId) || null,
    ),
    [costReviewed, setCostReviewed] = useState(
      seed?.costSource?.reviewed || false,
    ),
    [extra, setExtra] = useState(String(seed?.extraSaleCost ?? 0)),
    [commission, setCommission] = useState(
      String(seed?.commissionPercent ?? 0),
    ),
    [discount, setDiscount] = useState(String(seed?.discountPercent ?? 0));
  const [productId, setProduct] = useState(
      seed?.productId || (coffee ? "cafe-pergamino-seco" : ""),
    ),
    [marketId, setMarket] = useState(seed?.marketId || "");
  const [priceMode, setPriceMode] = useState<"history" | "manual">(
      seed?.priceMode || "history",
    ),
    [manualPrice, setManualPrice] = useState(seed?.manualPrice || ""),
    [month, setMonth] = useState(seed?.month || new Date().getMonth() + 1);
  const [plantDate, setPlantDate] = useState(farm.plantingDate),
    [days, setDays] = useState(""),
    [status, setStatus] = useState(""),
    [saved, setSaved] = useState<Record<string, unknown>[]>([]);
  const catalog = useData<Catalog>("/api/catalog");
  const products = useMemo(
    () =>
      catalog.data?.products.filter((p) => {
        const name = fold(p.name),
          c = fold(crop.crop);
        if (c === "arroz" || c === "cana panelera") return false; // Paddy / cane cannot be priced as milled rice / panela.
        if (c === "frijol")
          return name.startsWith("frijol") && !/verde|enlatad/.test(name);
        if (c === "maiz")
          return (
            name.startsWith("maiz") &&
            /cascara|seco/.test(name) &&
            !name.includes("trillado")
          );
        if (c === "cebolla de rama") return name.includes("cebolla junca");
        if (c === "cebolla de bulbo") return name.includes("cebolla cabezona");
        return name === c || name.startsWith(c + " ");
      }) || [],
    [catalog.data, crop.crop],
  );
  const resolvedProduct = coffee
    ? "cafe-pergamino-seco"
    : products.find((p) => p.id === productId)?.id ||
      products.find(
        (p) =>
          fold(crop.variety).includes("hass") && fold(p.name).includes("hass"),
      )?.id ||
      products[0]?.id ||
      "";
  const detail = useData<{ markets: MarketPrice[] }>(
    resolvedProduct && !coffee ? "/api/products/" + resolvedProduct : null,
  );
  const marketOptions = [...(detail.data?.markets || [])].sort(
    (a, b) =>
      (fold(a.region) === fold(data.municipality.department) ? 0 : 1) -
        (fold(b.region) === fold(data.municipality.department) ? 0 : 1) ||
      a.name.localeCompare(b.name, "es"),
  );
  const selectedMarket =
    marketOptions.find((m) => m.id === marketId) || marketOptions[0];
  const seasonal = useData<Seasonality>(
    resolvedProduct && (coffee || selectedMarket)
      ? `/api/planning/seasonality?product=${encodeURIComponent(resolvedProduct)}&market=${encodeURIComponent(coffee ? "fnc-national" : selectedMarket!.id)}`
      : null,
  );
  const historical = seasonal.data
    ? seasonalPrices(seasonal.data, month)
    : null;
  const templates = data.templates.filter(
    (t) => fold(t.crop) === fold(crop.crop),
  );
  const calendars = data.calendars.filter(
    (c) => fold(c.crop) === fold(crop.crop),
  );
  const validNumbers = [
    area,
    yieldKg,
    loss,
    uncertainty,
    extra,
    commission,
    discount,
  ].every((s) => s !== "" && Number.isFinite(+s));
  const goodCosts =
    costs.every(
      (c) => c.amount !== "" && Number.isFinite(+c.amount) && +c.amount >= 0,
    ) && costs.some((c) => +c.amount > 0);
  const valid =
    validNumbers &&
    +area > 0 &&
    +area <= 100000 &&
    +yieldKg > 0 &&
    +yieldKg <= 1000000 &&
    +loss >= 0 &&
    +loss < 100 &&
    +uncertainty >= 0 &&
    +uncertainty < 100 &&
    +extra >= 0 &&
    +commission >= 0 &&
    +commission < 100 &&
    +discount >= 0 &&
    +discount < 100 &&
    goodCosts;
  const prices =
    priceMode === "manual" &&
    manualPrice !== "" &&
    Number.isFinite(+manualPrice) &&
    +manualPrice > 0
      ? { low: +manualPrice, typical: +manualPrice, high: +manualPrice }
      : priceMode === "history"
        ? historical
        : null;
  const totalProductionCost =
      costs.reduce((s, c) => s + (+c.amount || 0), 0) * (+area || 0),
    totalCost = totalProductionCost + (+extra || 0),
    kg = (+area || 0) * (+yieldKg || 0) * (1 - (+loss || 0) / 100);
  const breakEven = valid ? totalCost / (kg * (1 - +commission / 100)) : null;
  const before =
    costs
      .filter((c) => c.timing === "before")
      .reduce((s, c) => s + (+c.amount || 0), 0) * (+area || 0);
  const results =
    valid && prices
      ? (["low", "typical", "high"] as const).map((key, i) => {
          const quantity = kg * (1 + ((i - 1) * +uncertainty) / 100),
            price =
              prices[key] * (priceMode === "history" ? 1 - +discount / 100 : 1),
            revenue = quantity * price,
            fees = (revenue * +commission) / 100;
          return {
            key,
            quantity,
            price,
            revenue,
            fees,
            profit: revenue - fees - totalCost,
          };
        })
      : null;
  useEffect(() => {
    try {
      let raw = localStorage.getItem(scenarioKey);
      if (!raw && scenarioKey === "agroamigo-scenarios-legacy-farm") {
        raw = localStorage.getItem("agroamigo-scenarios-v1");
        if (raw) localStorage.setItem(scenarioKey, raw);
      }
      const v = JSON.parse(raw || "[]");
      if (Array.isArray(v)) setSaved(v.slice(-6));
    } catch {}
  }, []);
  const loadTemplate = (id: string) => {
    const t = templates.find((t) => t.id === id);
    if (!t) return;
    setTemplate(t);
    setCosts(t.costs.map((c) => ({ ...c, amount: String(c.amount) })));
    setCostReviewed(false);
    setStatus(
      "Referencia de " +
        t.reference_year +
        " cargada. Revisa y actualiza cada costo.",
    );
  };
  const periodLabel =
    period === "annual"
      ? "Un año de cultivo en producción"
      : period === "establishment"
        ? "Período de establecimiento"
        : "Un ciclo de cultivo";
  const snapshot = () => ({
    name: crop.variety,
    municipality: data.municipality.name,
    municipalityId: data.municipality.id,
    createdAt: new Date().toISOString(),
    period: periodLabel,
    periodCode: period,
    planYear: managed?.planYear || String(new Date().getFullYear()),
    productId: resolvedProduct,
    marketId: selectedMarket?.id || "",
    manualPrice,
    areaHa: +area,
    yieldKgHa: +yieldKg,
    lossPercent: +loss,
    uncertaintyPercent: +uncertainty,
    costsPerHa: costs.map((c) => ({ ...c, amount: +c.amount })),
    costSource: template
      ? {
          document: template.document_id,
          templateId: template.id,
          page: template.source_page,
          year: template.reference_year,
          reviewed: costReviewed,
        }
      : null,
    extraSaleCost: +extra,
    commissionPercent: +commission,
    discountPercent: priceMode === "history" ? +discount : 0,
    priceMode,
    month,
    totalCost,
    breakEven,
    results,
    sourceDocuments: [
      crop.document_id,
      ...(seasonal.data?.years.map((y) => y.document_id) || []),
      ...(selectedMarket?.document_id ? [selectedMarket.document_id] : []),
    ],
  });
  const save = () => {
    if (!results) return;
    const row = snapshot(),
      next = [...saved, row].slice(-6);
    setSaved(next);
    try {
      localStorage.setItem(scenarioKey, JSON.stringify(next));
      setStatus("Escenario guardado en este navegador.");
    } catch {
      setStatus("No se pudo guardar en este navegador. Descarga el escenario.");
    }
  };
  const download = () => {
    if (/AgroAmigo(Android|IOS)\//.test(navigator.userAgent)) {
      window.location.href =
        "agroamigo-export://scenario?data=" +
        encodeURIComponent(JSON.stringify(snapshot(), null, 2));
      return;
    }
    const blob = new Blob([JSON.stringify(snapshot(), null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "escenario-agroamigo-" + bogotaToday() + ".json";
    a.click();
    URL.revokeObjectURL(url);
  };
  const guideDays =
    coffee && farm.floweringDate
      ? farm.elevation && +farm.elevation < 1200
        ? [196, 210]
        : farm.elevation && +farm.elevation > 1700
          ? [238, 252]
          : [196, 252]
      : null;
  const harvest =
    plantDate && days && +days > 0 && +days <= 3650
      ? addDays(plantDate, +days)
      : null;
  return (
    <>
      <div className="budget-header">
        <div>
          <span className="eyebrow">
            MIS CUENTAS · {data.municipality.name}
          </span>
          <h2>{crop.variety}</h2>
          <p>
            Parte de una referencia, cambia los supuestos y compara escenarios.
          </p>
        </div>
        <span className="source-badge">{periodLabel}</span>
      </div>
      <div className="budget-layout">
        <div className="budget-fields">
          <section className="panel">
            <div className="step-title">
              <span>1</span>
              <h3>Tu producción esperada</h3>
            </div>
            <div className="form-grid">
              <label className="form-field">
                Área (hectáreas)
                <input
                  type="number"
                  min="0.01"
                  max="100000"
                  step="any"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                />
              </label>
              <label className="form-field">
                Período que vas a presupuestar
                <select
                  value={period}
                  onChange={(e) => {
                    setPeriod(e.target.value);
                    if (e.target.value === "establishment") setYield("");
                  }}
                >
                  <option value="cycle">Un ciclo de cultivo</option>
                  {permanent && (
                    <option value="annual">
                      Un año, cultivo en producción
                    </option>
                  )}
                  <option value="establishment">
                    Establecimiento de un cultivo nuevo
                  </option>
                </select>
              </label>
              <label className="form-field">
                Cosecha de referencia (kg por hectárea)
                <input
                  type="number"
                  min="0"
                  max="1000000"
                  step="any"
                  value={yieldKg}
                  onChange={(e) => setYield(e.target.value)}
                />
                <small>
                  {crop.physical_state}. Ingresa lo que esperas obtener en ese
                  período.
                </small>
              </label>
              <label className="form-field">
                Pérdida o producto no vendible (%)
                <input
                  type="number"
                  min="0"
                  max="99"
                  value={loss}
                  onChange={(e) => setLoss(e.target.value)}
                />
              </label>
            </div>
            {crop.document_id ? (
              <div className="yield-note">
                <p>
                  <strong>Referencia EVA {crop.reference_year}:</strong>{" "}
                  {crop.yield_kg_ha
                    ? number(crop.yield_kg_ha) + " kg/ha"
                    : "Sin rendimiento disponible"}
                  , calculada con {number(crop.production_t)} toneladas /{" "}
                  {number(crop.harvested_ha)} hectáreas cosechadas. Corresponde
                  a {crop.variety.toLowerCase()} en el municipio.
                </p>
                <EvidenceLink
                  id={crop.document_id}
                  municipality={data.municipality.id}
                >
                  Comprobar rendimiento y unidades
                </EvidenceLink>
              </div>
            ) : (
              <p className="inline-note">
                No hay una referencia municipal comparable. Ingresa tu
                rendimiento y el estado del producto; estos serán supuestos
                propios.
              </p>
            )}
            {permanent && (
              <p className="inline-warning">
                El rendimiento de EVA corresponde a áreas cosechadas, no a una
                siembra nueva. Un cultivo permanente puede tardar varios años en
                producir; para establecimiento, ingresa la cosecha prevista para
                ese período.
              </p>
            )}
          </section>
          <section className="panel">
            <div className="step-title">
              <span>2</span>
              <h3>Lo que cuesta producir</h3>
            </div>
            {coffee && <CoffeeCostReference />}
            {templates.length > 0 ? (
              <label className="form-field">
                Comenzar con una referencia publicada
                <select
                  value={template?.id || ""}
                  onChange={(e) => loadTemplate(e.target.value)}
                >
                  <option value="">
                    Elegir una estructura de costos (opcional)
                  </option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.region} · {t.reference_year}
                      {t.municipalities.includes(data.municipality.id)
                        ? " · incluye tu municipio"
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p>
                Ingresa tus costos por hectárea. No tenemos una estructura
                numérica verificada para este cultivo; puedes consultar los
                insumos de tu departamento.
              </p>
            )}
            {template && (
              <div className="cost-reference">
                <strong>
                  UPRA · {template.region} · valores de{" "}
                  {template.reference_year}
                </strong>
                <p>
                  {template.production_system}. {template.notes}
                </p>
                <p>
                  Rendimiento del estudio: {number(template.yield_kg_ha)} kg/ha.
                  No reemplaza el rendimiento local de tu escenario.
                </p>
                <EvidenceLink
                  id={template.document_id}
                  page={template.source_page}
                >
                  Ver tabla original de costos
                </EvidenceLink>
              </div>
            )}
            <p className="field-help">
              Valores en COP por hectárea. Incluye el trabajo propio, arriendo y
              otros gastos que apliquen.
            </p>
            <div className="budget-costs">
              {costs.map((c, i) => (
                <div key={i} className="cost-row">
                  <label className="form-field">
                    {c.label}
                    <input
                      aria-label={c.label + " por hectárea"}
                      type="number"
                      min="0"
                      step="any"
                      placeholder="COP / ha"
                      value={c.amount}
                      onChange={(e) => {
                        setCosts((old) =>
                          old.map((r, k) =>
                            k === i ? { ...r, amount: e.target.value } : r,
                          ),
                        );
                        setCostReviewed(false);
                      }}
                    />
                  </label>
                  <label className="form-field">
                    Cuándo se paga
                    <select
                      aria-label={"Cuándo se paga " + c.label}
                      value={c.timing}
                      onChange={(e) =>
                        setCosts((old) =>
                          old.map((r, k) =>
                            k === i
                              ? {
                                  ...r,
                                  timing: e.target.value as
                                    | "before"
                                    | "harvest",
                                }
                              : r,
                          ),
                        )
                      }
                    >
                      <option value="before">Antes de cosechar</option>
                      <option value="harvest">En cosecha / venta</option>
                    </select>
                  </label>
                </div>
              ))}
            </div>
            <label className="check-field">
              <input
                type="checkbox"
                checked={costReviewed}
                onChange={(e) => setCostReviewed(e.target.checked)}
              />{" "}
              Revisé estos costos para mi finca y el período del escenario
            </label>
            <Link
              className="evidence-link"
              href={
                "/insumos?department=" +
                encodeURIComponent(data.municipality.department)
              }
            >
              Consultar precios de insumos de mi departamento →
            </Link>
          </section>
          <section className="panel">
            <div className="step-title">
              <span>3</span>
              <h3>El precio y los gastos de venta</h3>
            </div>
            <div
              className="segmented-control"
              role="group"
              aria-label="Origen del precio"
            >
              <button
                className={priceMode === "history" ? "active" : ""}
                onClick={() => setPriceMode("history")}
              >
                Usar la historia
              </button>
              <button
                className={priceMode === "manual" ? "active" : ""}
                onClick={() => setPriceMode("manual")}
              >
                Ingresar mi precio
              </button>
            </div>
            {priceMode === "history" ? (
              <>
                {!coffee && (
                  <label className="form-field">
                    Producto y presentación que venderías
                    <select
                      value={resolvedProduct}
                      onChange={(e) => {
                        setProduct(e.target.value);
                        setMarket("");
                      }}
                    >
                      <option value="">Selecciona una presentación</option>
                      {products.map((p) => (
                        <option value={p.id} key={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <small>
                      Confirma que la variedad, calidad y estado coincidan. No
                      se convierten productos procesados en cosecha en finca.
                    </small>
                  </label>
                )}
                {!coffee && selectedMarket && (
                  <label className="form-field">
                    Mercado de referencia
                    <select
                      value={selectedMarket.id}
                      onChange={(e) => setMarket(e.target.value)}
                    >
                      {marketOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {catalog.error || detail.error || seasonal.error ? (
                  <ErrorState
                    message={catalog.error || detail.error || seasonal.error}
                    retry={() => {
                      catalog.retry();
                      detail.retry();
                      seasonal.retry();
                    }}
                  />
                ) : !resolvedProduct ? (
                  <p className="inline-note">
                    No encontramos una cotización equivalente para este estado
                    del producto. Usa “Ingresar mi precio” para simularlo.
                  </p>
                ) : seasonal.loading || detail.loading ? (
                  <p role="status">Buscando historia comparable…</p>
                ) : null}
                <div className="form-grid">
                  <label className="form-field">
                    Mes de venta que simulas
                    <select
                      value={month}
                      onChange={(e) => setMonth(+e.target.value)}
                    >
                      {MONTHS.map((m, i) => (
                        <option key={m} value={i + 1}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="form-field">
                    Descuento frente a la referencia (%)
                    <input
                      type="number"
                      min="0"
                      max="99"
                      value={discount}
                      onChange={(e) => setDiscount(e.target.value)}
                    />
                    <small>
                      Por calidad, intermediación o diferencia con el precio en
                      finca. Es tu supuesto.
                    </small>
                  </label>
                </div>
                {!coffee && (
                  <p className="inline-warning">
                    SIPSA informa precios mayoristas. Ajusta el descuento y los
                    gastos: ese precio no equivale al pago al agricultor.
                  </p>
                )}
                {seasonal.data && (
                  <SeasonalChart
                    data={seasonal.data}
                    month={month}
                    onMonth={setMonth}
                  />
                )}
              </>
            ) : (
              <label className="form-field">
                Precio que recibirías por kg (COP)
                <input
                  type="number"
                  min="1"
                  value={manualPrice}
                  onChange={(e) => setManualPrice(e.target.value)}
                  placeholder="Precio acordado o supuesto"
                />
                <small>
                  Usa la misma presentación y calidad que tu cosecha vendible.
                  No se aplica el descuento frente al mayorista.
                </small>
              </label>
            )}
            <div className="form-grid">
              <label className="form-field">
                Gastos adicionales de venta, total (COP)
                <input
                  type="number"
                  min="0"
                  value={extra}
                  onChange={(e) => setExtra(e.target.value)}
                />
                <small>
                  Transporte, empaque u otros que aún no estén incluidos arriba.
                </small>
              </label>
              <label className="form-field">
                Comisión sobre la venta (%)
                <input
                  type="number"
                  min="0"
                  max="99"
                  value={commission}
                  onChange={(e) => setCommission(e.target.value)}
                />
              </label>
              <label className="form-field">
                Variación de cosecha para escenarios (± %)
                <input
                  type="number"
                  min="0"
                  max="99"
                  value={uncertainty}
                  onChange={(e) => setUncertainty(e.target.value)}
                />
                <small>Supuesto editable, no un intervalo estadístico.</small>
              </label>
            </div>
          </section>
        </div>
        <aside className="budget-summary">
          <section className="panel summary-sticky">
            <span className="eyebrow">
              <IoCalculatorOutline /> ASÍ QUEDAN TUS CUENTAS
            </span>
            <h3>{periodLabel}</h3>
            <dl className="summary-numbers">
              <div>
                <dt>Cosecha vendible estimada</dt>
                <dd>
                  {validNumbers &&
                  +area > 0 &&
                  +yieldKg >= 0 &&
                  +loss >= 0 &&
                  +loss < 100
                    ? number(kg) + " kg"
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Costo total del escenario</dt>
                <dd>{goodCosts ? money(totalCost) : "Completa tus costos"}</dd>
              </div>
              <div>
                <dt>Asignado antes de cosecha</dt>
                <dd>{goodCosts ? money(before) : "—"}</dd>
              </div>
            </dl>
            <div className="break-even">
              <span>Para cubrir tus costos necesitas</span>
              <strong>
                {breakEven !== null ? money(breakEven) : "—"}{" "}
                <small>/ kg</small>
              </strong>
              <p>Precio de venta antes de comisión, por kilo vendible.</p>
            </div>
            {!costReviewed && (
              <p className="inline-warning">
                {template
                  ? `Costos de referencia de ${template.reference_year}, pendientes de revisar.`
                  : "Completa y revisa tus costos para interpretar el resultado."}
              </p>
            )}
            {results ? (
              <div className="earnings-scenarios">
                {results.map((r, i) => (
                  <article
                    key={r.key}
                    className={
                      (i === 1 ? "typical " : "") + (r.profit < 0 ? "loss" : "")
                    }
                  >
                    <span>
                      {
                        [
                          "Escenario bajo",
                          "Escenario central",
                          "Escenario alto",
                        ][i]
                      }
                    </span>
                    <strong>{money(r.profit)}</strong>
                    <p>
                      {r.profit < 0
                        ? "Saldo negativo"
                        : "Saldo después de costos"}
                    </p>
                    <small>
                      {number(r.quantity)} kg × {money(r.price)}/kg
                    </small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="inline-note">
                Completa producción, costos y un precio válido para calcular el
                saldo.
              </p>
            )}
            {results && (
              <p className="privacy-note">
                Se combinan{" "}
                {priceMode === "history"
                  ? "los percentiles 25, 50 y 75 de cambios históricos del precio"
                  : "el precio que ingresaste"}{" "}
                con cosechas de −{uncertainty} %, sin cambio y +{uncertainty} %.
                Son escenarios de planeación; no garantizan ingresos ni
                compradores.
              </p>
            )}
            {onApply && (
              <button
                type="button"
                className="button primary"
                disabled={!results}
                onClick={() => {
                  if (!results) return;
                  setStatus(
                    onApply(snapshot())
                      ? "Presupuesto aplicado a este cultivo. Consulta el resumen de tu finca."
                      : "El área supera el espacio disponible en la finca. Revisa las hectáreas.",
                  );
                }}
              >
                Aplicar presupuesto a este cultivo
              </button>
            )}
            <button
              className="button secondary"
              disabled={!results}
              onClick={save}
            >
              <IoSaveOutline /> Guardar escenario
            </button>
            <button
              className="button secondary"
              disabled={!results}
              onClick={download}
            >
              <IoDownloadOutline /> Descargar mis cuentas
            </button>
            {status && (
              <p role="status" className="save-status">
                {status}
              </p>
            )}
            <EvidenceLink id="planning-method">
              Ver fórmulas y supuestos
            </EvidenceLink>
          </section>
        </aside>
      </div>
      <section className="panel harvest-panel">
        <div className="step-title">
          <span>4</span>
          <h3>Cuándo sembrar y esperar cosecha</h3>
        </div>
        {calendars.length ? (
          <>
            <p>
              Calendario histórico de {data.municipality.department}. Muestra
              cómo se distribuyó el área durante {calendars[0].reference_year},
              no la fecha óptima para este año.
            </p>
            <div className="calendar-scroll">
              <table className="data-table calendar-table">
                <thead>
                  <tr>
                    <th>Área (%)</th>
                    {MONTHS.map((m) => (
                      <th key={m}>{m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {calendars.map((c) => (
                    <tr key={c.activity}>
                      <th>{c.activity}</th>
                      {c.percentages.map((v, i) => (
                        <td
                          key={i}
                          style={{
                            backgroundColor: `rgba(43,112,70,${Math.max(0.025, (v / 100) * 0.8)})`,
                          }}
                        >
                          {number(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <EvidenceLink
              id={calendars[0].document_id}
              department={data.municipality.department_id}
            >
              Comprobar calendario de UPRA
            </EvidenceLink>
          </>
        ) : (
          <p>
            No hay calendario departamental integrado para este cultivo. No
            inferimos una temporada a partir de otros cultivos.
          </p>
        )}
        {coffee && guideDays ? (
          <div className="harvest-estimate">
            <h4>Ventana orientativa desde tu floración</h4>
            <strong>
              {dateLabel(addDays(farm.floweringDate, guideDays[0])!)} a{" "}
              {dateLabel(addDays(farm.floweringDate, guideDays[1])!)}
            </strong>
            <p>
              Cenicafé describe diferencias de 28 a 36 semanas según altitud. Se
              usa la floración que registraste, no la fecha de siembra. Verifica
              la madurez en el cultivo.
            </p>
            <EvidenceLink id="coffee-development" page={2}>
              Ver estudio y alcance del cálculo
            </EvidenceLink>
          </div>
        ) : coffee ? (
          <p>
            Registra la floración principal en{" "}
            <Link href="/farm">Mi finca</Link> para estimar una ventana
            orientativa de cosecha.
          </p>
        ) : null}
        <details className="source-explanation">
          <summary>Simular una fecha con el ciclo que conoces</summary>
          <div className="form-grid">
            <label className="form-field">
              Fecha de siembra / inicio
              <input
                type="date"
                value={plantDate}
                onChange={(e) => setPlantDate(e.target.value)}
              />
            </label>
            <label className="form-field">
              Días hasta cosecha que esperas
              <input
                type="number"
                min="1"
                max="3650"
                value={days}
                onChange={(e) => setDays(e.target.value)}
                placeholder="Según tu variedad y zona"
              />
            </label>
          </div>
          {harvest && (
            <p>
              Fecha calculada: <strong>{dateLabel(harvest)}</strong>. Es la suma
              de tus días esperados; no indica madurez observada.
            </p>
          )}
          {fold(crop.crop) === "papa" && (
            <p>
              Para la variedad Alhaja adaptada al Nudo de los Pastos, AGROSAVIA
              publica 120 días.{" "}
              <EvidenceLink id="potato-alhaja" page={21}>
                Consultar la ficha específica
              </EvidenceLink>
            </p>
          )}
        </details>
      </section>
      {saved.length > 0 && (
        <section className="saved-scenarios">
          <div className="section-heading">
            <div>
              <h2>Escenarios que guardaste</h2>
              <p>Compara área, período y supuestos antes de comparar saldos.</p>
            </div>
            <button
              className="button secondary"
              onClick={() => {
                setSaved([]);
                localStorage.removeItem(scenarioKey);
              }}
            >
              Borrar escenarios
            </button>
          </div>
          <div className="saved-scenario-grid">
            {saved.map((r, i) => (
              <article className="panel" key={i}>
                <h3>{String(r.name)}</h3>
                <p>
                  {String(r.municipality)} · {number(Number(r.areaHa))} ha
                </p>
                <span className="source-badge">{String(r.period)}</span>
                <p>Costo: {money(Number(r.totalCost))}</p>
                <p>Equilibrio: {money(Number(r.breakEven))}/kg</p>
                <strong>
                  Saldo central:{" "}
                  {money(
                    Number(
                      (r.results as { profit: number }[])?.[1]?.profit || 0,
                    ),
                  )}
                </strong>
                <p className="privacy-note">
                  Guardado{" "}
                  {new Date(String(r.createdAt)).toLocaleDateString("es-CO")}.
                  Conserva los supuestos del momento de guardado.
                </p>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
