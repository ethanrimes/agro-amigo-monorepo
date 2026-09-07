"use client";
import Link from "next/link";
import { CropPicture } from "./CropPicture";
import {
  IoArrowForward,
  IoHeart,
  IoHeartOutline,
  IoArrowUp,
  IoArrowDown,
  IoRefresh,
  IoLeafOutline,
  IoStorefrontOutline,
  IoInformationCircleOutline,
} from "react-icons/io5";
import { usePreferences } from "./Preferences";
import { change, money, dateLabel, type Product } from "@/lib/market-types";
export function RoleSwitch() {
  const { role, setRole } = usePreferences();
  return (
    <div className="role-switch" aria-label="¿Cómo usas AgroAmigo?">
      <button
        aria-pressed={role === "farmer"}
        className={role === "farmer" ? "selected" : ""}
        onClick={() => setRole("farmer")}
      >
        <IoLeafOutline /> Soy productor
      </button>
      <button
        aria-pressed={role === "buyer"}
        className={role === "buyer" ? "selected" : ""}
        onClick={() => setRole("buyer")}
      >
        <IoStorefrontOutline /> Soy comprador
      </button>
    </div>
  );
}
export function Change({
  price,
  previous,
  label = "vs. mes anterior",
}: {
  price: number;
  previous: number | null;
  label?: string;
}) {
  const delta = change(price, previous);
  if (delta === null)
    return <span className="no-change">Sin comparación anterior</span>;
  return (
    <span className={"price-change " + (delta >= 0 ? "up" : "down")}>
      {delta >= 0 ? <IoArrowUp /> : <IoArrowDown />}
      {Math.abs(delta).toFixed(1).replace(".", ",")}% <span>{label}</span>
    </span>
  );
}
export function ProductCard({ product }: { product: Product }) {
  const { saved, toggleSaved, role } = usePreferences();
  const active = saved.includes(product.id);
  return (
    <article className="product-card">
      <Link className="product-image-link" href={"/product/" + product.id}>
        <CropPicture
          imageKey={product.image_key}
          name={product.name}
          category={product.category}
        />
        <span className="product-category">{product.category}</span>
      </Link>
      <button
        className={"save-button " + (active ? "is-saved" : "")}
        aria-label={`${active ? "Quitar" : "Guardar"} ${product.name}`}
        aria-pressed={active}
        onClick={() => toggleSaved(product.id)}
      >
        {active ? <IoHeart /> : <IoHeartOutline />}
      </button>
      <div className="product-card-body">
        <Link href={"/product/" + product.id} className="product-name">
          {product.name}
        </Link>
        <span className="product-date">
          Promedio mensual · {dateLabel(product.date, true)}
        </span>
        <div className="product-price">
          {money(product.price)} <span>/ kg</span>
        </div>
        <Change price={product.price} previous={product.previous_price} />
        <Link href={"/product/" + product.id} className="product-card-footer">
          <span>
            {role === "buyer"
              ? "Comparar para comprar"
              : "Ver precios por mercado"}
          </span>
          <IoArrowForward />
        </Link>
      </div>
    </article>
  );
}
export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <div className="empty-state" role="alert">
      <IoInformationCircleOutline />
      <h3>No pudimos cargar los datos</h3>
      <p>{message}</p>
      <button className="button primary" onClick={retry}>
        <IoRefresh /> Volver a intentar
      </button>
    </div>
  );
}
export function LoadingCards() {
  return (
    <div className="product-grid" role="status" aria-label="Cargando precios">
      {[1, 2, 3, 4].map((x) => (
        <div className="skeleton-card" key={x}>
          <div />
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
export function SectionTitle({
  eyebrow,
  title,
  href,
  link,
}: {
  eyebrow?: string;
  title: string;
  href?: string;
  link?: string;
}) {
  return (
    <div className="section-title">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {href && (
        <Link href={href} className="text-link">
          {link || "Ver todos"} <IoArrowForward />
        </Link>
      )}
    </div>
  );
}
export function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="notice">
      <IoInformationCircleOutline />
      <p>{children}</p>
    </div>
  );
}
