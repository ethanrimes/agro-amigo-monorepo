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
  IoInformationCircleOutline,
} from "react-icons/io5";
import { usePreferences } from "./Preferences";
import { change } from "@/lib/market-types";
import {
  catalogBasis,
  catalogCurrency,
  catalogDate,
  catalogHref,
  catalogIdentity,
  catalogPriceNumber,
  catalogSavedKey,
  catalogUnit,
  type CatalogCard,
} from "@/lib/catalog-display";
import styles from "./catalog.module.css";
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
export function ProductCard({
  product,
  detailReturnTo,
}: {
  product: CatalogCard;
  detailReturnTo?: string;
}) {
  const { saved, toggleSaved } = usePreferences();
  const savedKey = catalogSavedKey(product);
  const active = saved.includes(savedKey);
  const href = catalogHref(product, detailReturnTo);
  return (
    <article
      className={`product-card ${styles.card}`}
      data-catalog-identity={catalogIdentity(product)}
      data-product-id={product.id}
    >
      <Link className="product-image-link" href={href}>
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
        onClick={() => toggleSaved(savedKey)}
      >
        {active ? <IoHeart /> : <IoHeartOutline />}
      </button>
      <div className="product-card-body">
        <Link href={href} className="product-name">
          {product.name}
        </Link>
        <span className="product-date">{catalogDate(product.date)}</span>
        <div
          className="product-price"
          data-price={product.price}
          data-currency={catalogCurrency(product)}
        >
          <span className={styles.currency}>{catalogCurrency(product)}</span>
          <strong className={styles.amount}>
            {catalogPriceNumber(product)}
          </strong>
          <span className={styles.unit}>{"/ " + catalogUnit(product)}</span>
        </div>
        <p className={styles.basis}>{catalogBasis(product)}</p>
        {product.kind === "official-reference" && product.market && (
          <p className={styles.market}>{product.market}</p>
        )}
        <Change
          price={product.price}
          previous={product.previous_price}
          label={
            product.period === "daily" || product.kind === "official-reference"
              ? "vs. referencia anterior"
              : "vs. mes anterior"
          }
        />
        <Link href={href} className="product-card-footer">
          <span>Ver producto</span>
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
