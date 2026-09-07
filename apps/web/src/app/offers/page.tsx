"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  IoAddOutline,
  IoSwapHorizontalOutline,
  IoCheckmarkCircleOutline,
} from "react-icons/io5";
import { usePreferences } from "@/components/marketplace/Preferences";
import { RoleSwitch } from "@/components/marketplace/Shared";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { offerResult, bogotaToday } from "@/lib/planning-math";
import { money, number, dateLabel } from "@/lib/market-types";
import type { Offer } from "@/lib/planning-types";
function blank(id: string): Offer {
  return {
    id,
    name: "",
    price: "",
    acceptedKg: "100",
    deductionPercent: "0",
    transport: "0",
    packaging: "0",
    fees: "0",
    paymentDays: "0",
    expires: "",
    quality: "",
    pickup: false,
  };
}
export default function OffersPage() {
  const { role } = usePreferences(),
    buyer = role === "buyer";
  const [offers, setOffers] = useState<Offer[]>([blank("1"), blank("2")]),
    [product, setProduct] = useState(""),
    [available, setAvailable] = useState("100"),
    [unit, setUnit] = useState("1"),
    [loaded, setLoaded] = useState(false),
    [status, setStatus] = useState("");
  useEffect(() => {
    try {
      const r = JSON.parse(
        localStorage.getItem("agroamigo-private-offers-v1") || "null",
      );
      if (r) {
        if (typeof r.product === "string") setProduct(r.product.slice(0, 200));
        if (typeof r.available === "string") setAvailable(r.available);
        if (["1", "12.5", "125"].includes(r.unit)) setUnit(r.unit);
        if (Array.isArray(r.offers) && r.offers.length >= 2)
          setOffers(
            r.offers
              .slice(0, 3)
              .map((o: Record<string, unknown>, i: number) => {
                const row = blank(String(i + 1));
                for (const k of Object.keys(row) as (keyof Offer)[]) {
                  if (k === "pickup") row[k] = o[k] === true;
                  else if (typeof o[k] === "string")
                    row[k] = (o[k] as string).slice(0, 250);
                }
                return row;
              }),
          );
      }
    } catch {}
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (loaded)
      try {
        localStorage.setItem(
          "agroamigo-private-offers-v1",
          JSON.stringify({ product, available, unit, offers }),
        );
        setStatus("Guardado en este navegador");
      } catch {
        setStatus("No se pudo guardar en este navegador");
      }
  }, [product, available, unit, offers, loaded]);
  const set = (i: number, key: keyof Offer, value: string | boolean) =>
    setOffers((old) =>
      old.map((o, k) => (k === i ? { ...o, [key]: value } : o)),
    );
  const validQty =
    available !== "" &&
    Number.isFinite(+available) &&
    +available > 0 &&
    +available <= 1000000;
  const computed = offers.map((o) => {
    const normalized = {
      ...o,
      price: o.price === "" ? "" : String(+o.price / +unit),
    };
    const r = validQty ? offerResult(normalized, +available) : null;
    return r
      ? {
          ...r,
          total: buyer ? r.gross - r.deduction + r.costs : r.net,
          perKg: buyer
            ? (r.gross - r.deduction + r.costs) / +o.acceptedKg
            : r.netKg,
        }
      : null;
  });
  const eligible = computed
    .map((r, i) => ({ r, i }))
    .filter((x) => x.r && !x.r.expired);
  eligible.sort((a, b) =>
    buyer ? a.r!.perKg - b.r!.perKg : b.r!.perKg - a.r!.perKg,
  );
  const best = eligible.length >= 2 ? eligible[0].i : -1;
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">COMPARA CON TODAS LAS CUENTAS</span>
          <h1>
            {buyer ? "¿Qué proveedor me conviene?" : "¿Qué oferta me deja más?"}
          </h1>
          <p>
            {buyer
              ? "Compara el costo por kilo recibido y las condiciones de cada proveedor."
              : "Compara el dinero que recibirías después de los gastos de vender."}
          </p>
        </div>
        <RoleSwitch />
      </div>
      <section className="panel offer-common">
        <span className="source-badge">
          Comparación privada · datos que tú ingresas
        </span>
        <div className="form-grid">
          <label className="form-field">
            Producto, variedad y calidad que comparas
            <input
              placeholder="Ej. café pergamino seco, factor 94"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              maxLength={200}
            />
          </label>
          <label className="form-field">
            {buyer
              ? "Cantidad que necesitas (kg)"
              : "Cantidad disponible para vender (kg)"}
            <input
              type="number"
              min="1"
              max="1000000"
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
            />
          </label>
          <label className="form-field">
            Unidad de las cotizaciones
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="1">Kilogramo</option>
              <option value="125">Carga de café de 125 kg</option>
              <option value="12.5">Arroba de café de 12,5 kg</option>
            </select>
            <small>La comparación final siempre se hace por kilogramo.</small>
          </label>
        </div>
        <p className="privacy-note">
          Confirma que las ofertas sean para la misma calidad y presentación.
          Son tus cotizaciones privadas; AgroAmigo no verifica ni publica
          compradores o proveedores.
        </p>
      </section>
      <div className={"offer-grid offers-" + offers.length}>
        {offers.map((o, i) => {
          const r = computed[i];
          return (
            <section
              className={
                "panel offer-editor " + (best === i ? "best-offer" : "")
              }
              key={o.id}
            >
              <div className="offer-card-heading">
                <span className="offer-number">{i + 1}</span>
                <h2>{o.name || `Oferta ${i + 1}`}</h2>
                {offers.length > 2 && (
                  <button
                    className="icon-button"
                    aria-label={"Quitar oferta " + (i + 1)}
                    onClick={() => setOffers(offers.filter((_, k) => k !== i))}
                  >
                    ×
                  </button>
                )}
              </div>
              {best === i && (
                <span className="offer-best-label">
                  <IoCheckmarkCircleOutline />
                  {buyer ? "Menor costo por kilo" : "Mayor pago neto por kilo"}
                </span>
              )}
              <label className="form-field">
                {buyer ? "Nombre del proveedor" : "Nombre del comprador"}
                <input
                  aria-label={"Nombre oferta " + (i + 1)}
                  maxLength={80}
                  value={o.name}
                  onChange={(e) => set(i, "name", e.target.value)}
                />
              </label>
              <label className="form-field">
                Precio ofrecido (COP /{" "}
                {unit === "1" ? "kg" : unit === "125" ? "carga" : "arroba"})
                <input
                  aria-label={"Precio oferta " + (i + 1)}
                  type="number"
                  min="1"
                  value={o.price}
                  onChange={(e) => set(i, "price", e.target.value)}
                />
              </label>
              <label className="form-field">
                Cantidad aceptada (kg)
                <input
                  aria-label={"Kilos oferta " + (i + 1)}
                  type="number"
                  min="0.01"
                  max={validQty ? +available : 1000000}
                  step="any"
                  value={o.acceptedKg}
                  onChange={(e) => set(i, "acceptedKg", e.target.value)}
                />
              </label>
              <details className="offer-conditions" open>
                <summary>Gastos, descuentos y pago</summary>
                <label className="form-field">
                  Descuento por calidad sobre el valor (%)
                  <input
                    aria-label={"Descuento oferta " + (i + 1)}
                    type="number"
                    min="0"
                    max="100"
                    value={o.deductionPercent}
                    onChange={(e) => set(i, "deductionPercent", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Transporte a tu cargo (COP)
                  <input
                    aria-label={"Transporte oferta " + (i + 1)}
                    type="number"
                    min="0"
                    value={o.transport}
                    onChange={(e) => set(i, "transport", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Empaque a tu cargo (COP)
                  <input
                    aria-label={"Empaque oferta " + (i + 1)}
                    type="number"
                    min="0"
                    value={o.packaging}
                    onChange={(e) => set(i, "packaging", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Comisiones y otros gastos (COP)
                  <input
                    aria-label={"Gastos oferta " + (i + 1)}
                    type="number"
                    min="0"
                    value={o.fees}
                    onChange={(e) => set(i, "fees", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Pago después de la entrega (días)
                  <input
                    aria-label={"Plazo oferta " + (i + 1)}
                    type="number"
                    min="0"
                    max="365"
                    value={o.paymentDays}
                    onChange={(e) => set(i, "paymentDays", e.target.value)}
                  />
                  <small>0 = pago al entregar.</small>
                </label>
                <label className="form-field">
                  Oferta vigente hasta
                  <input
                    aria-label={"Vigencia oferta " + (i + 1)}
                    type="date"
                    value={o.expires}
                    onChange={(e) => set(i, "expires", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Condiciones que debes confirmar
                  <textarea
                    rows={2}
                    maxLength={250}
                    value={o.quality}
                    onChange={(e) => set(i, "quality", e.target.value)}
                    placeholder="Recogida o entrega, rechazo por calidad, lugar…"
                  />
                </label>
              </details>
              {r ? (
                <div className={"offer-result " + (r.expired ? "expired" : "")}>
                  <span>
                    {buyer
                      ? "Costo total de compra"
                      : "Recibirías después de gastos"}
                  </span>
                  <strong>{money(r.total)}</strong>
                  <b>
                    {money(r.perKg)} / kg {buyer ? "recibido" : "aceptado"}
                  </b>
                  <p>
                    {r.paymentDays === 0
                      ? "Pago al entregar"
                      : `Pago ${r.paymentDays} días después de la entrega`}
                  </p>
                  {r.remainingKg > 0 && (
                    <p className="inline-warning">
                      Quedan {number(r.remainingKg)} kg{" "}
                      {buyer ? "por conseguir" : "sin vender"}. Este total cubre
                      solo {number(+o.acceptedKg)} kg.
                    </p>
                  )}
                  {r.expired ? (
                    <p className="inline-warning">
                      Oferta vencida el {dateLabel(o.expires)}. Se excluye de la
                      comparación.
                    </p>
                  ) : (
                    <small>
                      {o.expires
                        ? "Vigencia ingresada: " + dateLabel(o.expires)
                        : "Vigencia sin confirmar"}
                    </small>
                  )}
                  <details>
                    <summary>Ver el cálculo</summary>
                    <p>
                      {money(r.gross)} por el producto − {money(r.deduction)} de
                      descuento {buyer ? "+" : "−"} {money(r.costs)} de gastos ={" "}
                      {money(r.total)}.
                    </p>
                  </details>
                </div>
              ) : (
                <p className="inline-note">
                  Ingresa un precio y cantidades válidas. Los kilos aceptados no
                  pueden superar el total disponible; los gastos deben ser cero
                  o más.
                </p>
              )}
            </section>
          );
        })}
      </div>
      {offers.length < 3 && (
        <button
          className="button secondary show-more"
          onClick={() => setOffers([...offers, blank("3")])}
        >
          <IoAddOutline /> Agregar otra oferta
        </button>
      )}
      <section className="panel offer-explanation">
        <h3>El plazo y la cantidad también importan</h3>
        <p>
          Se destaca el {buyer ? "menor costo" : "mayor pago neto"} por kilo
          entre ofertas no vencidas. El dinero de una venta menor no equivale a
          vender toda la cosecha. El plazo se muestra por separado: no se asigna
          un costo de financiación ni se predice si pagarán.
        </p>
        <p>
          {buyer
            ? "El costo incluye producto menos descuentos, más gastos a tu cargo."
            : "El neto de la venta descuenta gastos de comercialización. Para calcular la utilidad también debes restar los costos de producir."}
        </p>
        <div className="form-actions">
          <EvidenceLink id="planning-method">Comprobar la fórmula</EvidenceLink>
          <Link className="button secondary" href="/plan?tab=budget">
            <IoCalculatorOutlineFallback /> Calcular costos de producción
          </Link>
        </div>
        <p className="privacy-note" role="status">
          {status}. No se enviaron ofertas a terceros.
        </p>
      </section>
    </>
  );
}
function IoCalculatorOutlineFallback() {
  return <IoSwapHorizontalOutline />;
}
