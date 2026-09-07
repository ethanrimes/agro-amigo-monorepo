"use client";
import { CoffeeCostReference } from "@/components/planning/CoffeeCostReference";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { useState } from "react";
import { DetailTabs, type InformationMode } from "./DetailTabs";
import { SupplyPanel } from "./SupplyPanel";
import { MapButton } from "./ColombiaMap";
import Link from "next/link";
import {
  IoShieldCheckmarkOutline,
  IoScaleOutline,
  IoLeafOutline,
  IoLocationOutline,
  IoHeartOutline,
  IoHeart,
  IoArrowBack,
} from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import { ErrorState, Notice } from "@/components/marketplace/Shared";
import { PriceChart } from "@/components/marketplace/PriceChart";
import { MarketList } from "@/components/marketplace/MarketList";
import { money, dateLabel, number, type Coffee } from "@/lib/market-types";
export function CoffeeDetail() {
  const [mode, setMode] = useState<InformationMode>("price");
  const { data, loading, error, retry } = useData<Coffee>("/api/coffee");
  const { saved, toggleSaved } = usePreferences();
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("125");
  const [factor, setFactor] = useState("94");
  const [offer, setOffer] = useState("");
  const [cost, setCost] = useState("0");
  const base =
    data?.factors.find((f) => f.factor === +factor)?.price ?? data?.price ?? 0;
  const valid =
    quantity !== "" &&
    Number.isFinite(+quantity) &&
    +quantity > 0 &&
    +quantity <= 1000000 &&
    Number.isFinite(+cost) &&
    +cost >= 0 &&
    (offer === "" || (Number.isFinite(+offer) && +offer > 0));
  const loads = (+quantity * +unit) / 125;
  const reference = loads * base;
  const offered = offer !== "" ? loads * +offer : null;
  const stale =
    data &&
    (Date.now() - new Date(data.date + "T12:00:00Z").getTime()) / 86400000 > 7;
  return (
    <>
      <Link href="/products" className="back-link">
        <IoArrowBack /> Volver a productos
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">EL VALOR DE CADA COSECHA</span>
          <h1>Café pergamino seco</h1>
          <p>La referencia oficial y tus cuentas, en un solo lugar.</p>
        </div>
        <button
          className="button secondary"
          aria-pressed={saved.includes("cafe-pergamino-seco")}
          onClick={() => toggleSaved("cafe-pergamino-seco")}
        >
          {saved.includes("cafe-pergamino-seco") ? (
            <IoHeart />
          ) : (
            <IoHeartOutline />
          )}
          {saved.includes("cafe-pergamino-seco")
            ? "Café guardado"
            : "Guardar café"}
        </button>
      </div>
      {loading ? (
        <div className="empty-state" role="status">
          Consultando el precio del café…
        </div>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <div className="detail-actions">
              <MapButton kind="product" id="cafe-pergamino-seco" />
            </div>
            <DetailTabs mode={mode} onChange={setMode} />
            {mode === "supply" ? (
              <SupplyPanel
                product="cafe-pergamino-seco"
                name="café pergamino seco"
              />
            ) : (
              <>
                <section className="coffee-hero">
                  <div className="coffee-hero-content">
                    <span className="coffee-reference-tag">
                      <IoShieldCheckmarkOutline /> REFERENCIA OFICIAL · FNC
                    </span>
                    <h2>Café pergamino seco</h2>
                    <div className="coffee-big-price">
                      {money(data.price)} <small>/ carga de 125 kg</small>
                    </div>
                    <p className="coffee-published">
                      Factor de rendimiento 94 · {money(data.price / 125)} por
                      kg
                      <br />
                      Referencia del {dateLabel(data.date)}{" "}
                      <EvidenceLink id={data.document_id}>
                        Ver publicación FNC ↗
                      </EvidenceLink>
                    </p>
                    {stale && (
                      <span className="stale-badge">
                        Último dato disponible: tiene más de 7 días.
                      </span>
                    )}
                  </div>
                  <img
                    className="coffee-hero-image"
                    src="/images/coffee.jpg"
                    alt="Cerezas de café en la planta, imagen ilustrativa del cultivo"
                  />
                </section>
                <div className="detail-grid">
                  <div>
                    <PriceChart
                      points={data.history}
                      label="El café en los últimos meses"
                      unit="COP / carga de 125 kg"
                    />
                    <p className="privacy-note">
                      Serie diaria nacional FNC. Solo se muestran fechas
                      publicadas; no se completan vacíos con precios estimados.
                    </p>
                    <MarketList markets={data.markets} coffee />
                  </div>
                  <aside>
                    <section className="panel calculator">
                      <span className="eyebrow">TUS CUENTAS, MÁS CLARAS</span>
                      <h2>¿Cuánto vale tu café?</h2>
                      <p>Compara una oferta con la referencia de la FNC.</p>
                      <p className="privacy-note">
                        Tabla de rendimiento del{" "}
                        {dateLabel(data.factors[0]?.date || data.date)}.
                      </p>
                      <div className="form-row">
                        <label className="form-field">
                          Cantidad
                          <input
                            type="number"
                            inputMode="decimal"
                            min="0.01"
                            max="1000000"
                            step="any"
                            value={quantity}
                            onChange={(e) => setQuantity(e.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          Unidad
                          <select
                            aria-label="Unidad"
                            value={unit}
                            onChange={(e) => setUnit(e.target.value)}
                          >
                            <option value="125">Cargas (125 kg)</option>
                            <option value="1">Kilos</option>
                            <option value="12.5">Arrobas (12,5 kg)</option>
                          </select>
                        </label>
                      </div>
                      <label className="form-field">
                        Factor de rendimiento
                        <select
                          aria-label="Factor de rendimiento"
                          value={factor}
                          onChange={(e) => setFactor(e.target.value)}
                        >
                          {(data.factors.length
                            ? data.factors
                            : [{ factor: 94, price: data.price }]
                          ).map((f) => (
                            <option value={f.factor} key={f.factor}>
                              {f.factor}
                              {f.factor === 94 ? " · Base FNC" : ""}
                            </option>
                          ))}
                        </select>
                        <small>
                          Usa el factor de tu análisis de trilla.{" "}
                          <EvidenceLink id="fnc-price" page={1}>
                            Ver tabla FNC
                          </EvidenceLink>
                        </small>
                      </label>
                      <label className="form-field">
                        Oferta del comprador por carga (COP)
                        <input
                          type="number"
                          inputMode="numeric"
                          min="1"
                          placeholder="Opcional. Ej.: 2.100.000"
                          value={offer}
                          onChange={(e) => setOffer(e.target.value)}
                        />
                        <small>
                          Ingresa una cotización que hayas recibido para la
                          misma calidad. No publicamos ofertas de compradores.
                        </small>
                      </label>
                      <label className="form-field">
                        Transporte y descuentos totales (COP)
                        <input
                          type="number"
                          inputMode="numeric"
                          min="0"
                          value={cost}
                          onChange={(e) => setCost(e.target.value)}
                        />
                      </label>
                      <div className="calculation-result" aria-live="polite">
                        <span>
                          {offered !== null
                            ? "Tu oferta, después de costos"
                            : "Referencia antes de costos"}
                        </span>
                        <strong>
                          {valid
                            ? money(
                                offered !== null ? offered - +cost : reference,
                              )
                            : "—"}
                        </strong>
                        {valid && (
                          <>
                            <p>
                              {number(+quantity * +unit)} kg de pergamino seco ·
                              Factor {factor}
                            </p>
                            <p>Referencia FNC total: {money(reference)}</p>
                            {offered !== null ? (
                              <p>
                                Oferta bruta{" "}
                                {offered >= reference
                                  ? "por encima"
                                  : "por debajo"}{" "}
                                de la referencia:{" "}
                                {money(Math.abs(offered - reference))}.
                              </p>
                            ) : (
                              <p>
                                Referencia menos costos:{" "}
                                {money(reference - +cost)}
                              </p>
                            )}
                          </>
                        )}
                      </div>
                      {!valid && (
                        <p className="invalid-input">
                          Revisa los valores: cantidad y oferta deben ser
                          positivas; los costos pueden ser cero.
                        </p>
                      )}
                      <p className="privacy-note">
                        Cálculo orientativo con la tabla nacional.
                        Bonificaciones, calidad en taza y condiciones de entrega
                        se acuerdan con el comprador.
                      </p>
                    </section>
                    <div className="explain-card">
                      <h3>¿Por qué cambia el precio?</h3>
                      <p>
                        La FNC considera el contrato C de Nueva York, la tasa de
                        cambio y la prima del café colombiano. La calidad y el
                        punto de entrega también influyen.
                      </p>
                      {data.exchange && (
                        <p>
                          TRM:{" "}
                          <strong>{money(data.exchange.price)} por USD</strong>
                          <br />
                          {dateLabel(data.exchange.date)} ·{" "}
                          <EvidenceLink id={data.exchange.document_id}>
                            Superfinanciera
                          </EvidenceLink>
                        </p>
                      )}
                      <Link href="/sources">
                        Conoce las fuentes del café ↗
                      </Link>
                    </div>
                  </aside>
                </div>
                <CoffeeCostReference />
                <Link className="button secondary" href="/plan?tab=budget">
                  Hacer el presupuesto de mi café →
                </Link>
                <div className="coffee-support">
                  <div>
                    <IoShieldCheckmarkOutline />
                    <h3>Garantía de compra</h3>
                    <p>
                      La red de cooperativas ofrece compra a precio de mercado.
                      Es una garantía de encontrar comprador, no un precio fijo
                      para cualquier café.
                    </p>
                  </div>
                  <div>
                    <IoScaleOutline />
                    <h3>Compara la misma calidad</h3>
                    <p>
                      El factor de rendimiento, la humedad, los defectos y las
                      bonificaciones pueden cambiar una oferta. Pergamino,
                      cereza y café tostado tienen unidades y condiciones
                      distintas.
                    </p>
                  </div>
                  <div>
                    <IoLocationOutline />
                    <h3>Confirma dónde entregas</h3>
                    <p>
                      La tabla regional corresponde a entrega en Almacafé.
                      Pregunta en el punto de compra por transporte, acopio y
                      descuentos aplicables.
                    </p>
                  </div>
                </div>
                <Notice>
                  La referencia de la FNC y una oferta privada son valores
                  diferentes. Esta demo no tiene un directorio de compradores
                  verificados ni cotizaciones comerciales activas.
                </Notice>
              </>
            )}
          </>
        )
      )}
    </>
  );
}
