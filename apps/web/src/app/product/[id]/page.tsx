"use client";
import { use, useState } from "react";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import Link from "next/link";
import { CropPicture } from "@/components/marketplace/CropPicture";
import { IoArrowBack, IoHeartOutline, IoHeart } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { usePreferences } from "@/components/marketplace/Preferences";
import {
  ErrorState,
  Notice,
  RoleSwitch,
} from "@/components/marketplace/Shared";
import { PriceChart } from "@/components/marketplace/PriceChart";
import { MarketList } from "@/components/marketplace/MarketList";
import {
  money,
  dateLabel,
  type Product,
  type MarketPrice,
  type Point,
} from "@/lib/market-types";
type Detail = { product: Product; markets: MarketPrice[]; history: Point[] };
export default function ProductPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { region, role, saved, toggleSaved } = usePreferences();
  const { data, loading, error, retry } = useData<Detail>(
    "/api/products/" +
      encodeURIComponent(id) +
      "?region=" +
      encodeURIComponent(region),
  );
  const [quantity, setQuantity] = useState("100");
  const [market, setMarket] = useState("");
  const [transport, setTransport] = useState("0");
  const markets = [...(data?.markets || [])].sort(
    (a, b) =>
      b.date.localeCompare(a.date) ||
      (role === "buyer" ? a.price - b.price : b.price - a.price),
  );
  const selected = markets.find((m) => m.id === market) || markets[0];
  const valid =
    quantity !== "" &&
    Number.isFinite(+quantity) &&
    +quantity > 0 &&
    +quantity <= 1000000 &&
    Number.isFinite(+transport) &&
    +transport >= 0;
  const total =
    selected && valid
      ? selected.price * +quantity + (role === "buyer" ? 1 : -1) * +transport
      : null;
  return (
    <>
      <Link href="/products" className="back-link">
        <IoArrowBack /> Volver a productos
      </Link>
      {loading ? (
        <div className="empty-state" role="status">
          Consultando precios del producto…
        </div>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <div className="detail-intro">
              <div className="detail-picture">
                <CropPicture
                  imageKey={data.product.image_key}
                  name={data.product.name}
                  category={data.product.category}
                />
              </div>
              <div>
                <span className="eyebrow">{data.product.category}</span>
                <h1>{data.product.name}</h1>
                <p>DANE · SIPSA · {region || "Colombia"}</p>
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
            <div className="page-heading">
              <p>Precios de venta mayorista, antes de costos de transporte.</p>
              <RoleSwitch />
            </div>
            <div className="detail-grid">
              <div>
                <PriceChart
                  points={data.history}
                  label="Así ha cambiado el precio"
                />
                <p className="privacy-note">
                  Promedio simple de mercados reportados en cada mes; la
                  cobertura puede cambiar. <EvidenceLink id={"price-"+id}>Comprobar precios en el documento</EvidenceLink>
                </p>
                <Link className="button secondary" href="/daily">Consultar precios del último boletín diario →</Link><MarketList markets={markets} />
              </div>
              <aside>
                <section className="panel calculator">
                  <span className="eyebrow">HAZ TUS CUENTAS</span>
                  <h2>
                    {role === "buyer"
                      ? "Calcula tu compra"
                      : "Estima el valor de tu producto"}
                  </h2>
                  <p>Usa una referencia para preparar tu negociación.</p>
                  <label className="form-field">
                    Mercado de referencia
                    <select
                      aria-label="Mercado de referencia"
                      value={selected?.id || ""}
                      onChange={(e) => setMarket(e.target.value)}
                    >
                      {markets.map((m) => (
                        <option value={m.id} key={m.id}>
                          {m.name} · {money(m.price)}/kg
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="form-field">
                    Cantidad en kilos
                    <input
                      inputMode="decimal"
                      type="number"
                      min="1"
                      max="1000000"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                    />
                  </label>
                  <label className="form-field">
                    Transporte total (COP)
                    <input
                      inputMode="numeric"
                      type="number"
                      min="0"
                      value={transport}
                      onChange={(e) => setTransport(e.target.value)}
                    />
                    <small>
                      {role === "buyer"
                        ? "Se suma al valor de la compra."
                        : "Se descuenta del valor de referencia."}
                    </small>
                  </label>
                  <div className="calculation-result" aria-live="polite">
                    <span>
                      {role === "buyer"
                        ? "Presupuesto estimado"
                        : "Valor de referencia menos transporte"}
                    </span>
                    <strong>{total !== null ? money(total) : "—"}</strong>
                    <p>
                      {selected
                        ? `Referencia del ${dateLabel(selected.date)}.`
                        : "Selecciona otro departamento para encontrar precios."}
                    </p>
                  </div>
                  {!valid && (
                    <p className="invalid-input">
                      Ingresa una cantidad positiva y costos de transporte de
                      cero o más.
                    </p>
                  )}
                  <p className="privacy-note">
                    Es un cálculo orientativo. No incluye intermediación,
                    empaque, pérdidas ni otros costos. No es una oferta de
                    compra.
                  </p>
                </section>
                <div className="explain-card">
                  <h3>La distancia también cuenta</h3>
                  <p>
                    El mercado con el mejor precio puede estar más lejos.
                    Compara el valor final después del transporte y confirma las
                    condiciones con quien compra.
                  </p>
                  <Link href="/offers">
                    Compara tus ofertas →
                  </Link>
                </div>
              </aside>
            </div>
            <Notice>
              Los precios corresponden al mercado mayorista. No representan el
              pago que recibe el productor en finca ni garantizan disponibilidad
              de producto.
            </Notice>
          </>
        )
      )}
    </>
  );
}
