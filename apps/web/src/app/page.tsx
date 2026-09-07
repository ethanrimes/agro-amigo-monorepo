"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  IoArrowForward,
  IoSearchOutline,
  IoCafeOutline,
  IoShieldCheckmarkOutline,
  IoLocationOutline,
  IoCalendarOutline,
  IoLeafOutline,
} from "react-icons/io5";
import { usePreferences } from "@/components/marketplace/Preferences";
import {
  RoleSwitch,
  ProductCard,
  SectionTitle,
  ErrorState,
  LoadingCards,
  Change,
} from "@/components/marketplace/Shared";
import { useData } from "@/components/marketplace/useData";
import {
  dateLabel,
  money,
  type Catalog,
  type Coffee,
} from "@/lib/market-types";
import { HomeActions } from "@/components/planning/HomeActions";
export default function Home() {
  const { role, region } = usePreferences();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const catalog = useData<Catalog>(
    "/api/catalog?region=" + encodeURIComponent(region),
  );
  const coffee = useData<Coffee>("/api/coffee");
  return (
    <>
      <div className="welcome-row">
        <div>
          <span className="eyebrow">BIENVENIDO A AGROAMIGO</span>
          <p>Un buen día empieza con buena información.</p>
        </div>
        <RoleSwitch />
      </div>
      <section className="hero">
        <img
          className="hero-photo"
          src="/images/farm.jpg"
          alt="Cultivos y campos verdes al amanecer"
          fetchPriority="high"
        />
        <div className="hero-shade" />
        <div className="hero-content">
          <span className="hero-kicker">
            <span /> MÁS CERCA DEL CAMPO
          </span>
          <h1>
            {role === "farmer" ? (
              <>
                Tu cosecha vale.
                <br />
                Conoce su precio.
              </>
            ) : (
              <>
                Compra informado.
                <br />
                Crece con el campo.
              </>
            )}
          </h1>
          <p>
            {role === "farmer"
              ? "Consulta precios, compara mercados y lleva el valor de tu trabajo a la próxima negociación."
              : "Compara precios de referencia y calcula tus compras de productos del campo colombiano."}
          </p>
          <form
            className="hero-search"
            onSubmit={(e) => {
              e.preventDefault();
              router.push("/products?q=" + encodeURIComponent(search));
            }}
          >
            <IoSearchOutline />
            <input
              aria-label="Buscar un producto"
              placeholder="¿Qué producto buscas?"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button aria-label="Buscar producto" type="submit">
              <IoArrowForward />
            </button>
          </form>
          <span className="hero-examples">
            Por ejemplo: café, aguacate, papa o plátano
          </span>
        </div>
        <span className="hero-location">
          <IoLocationOutline /> La fuerza de nuestra tierra
        </span>
      </section>
      <div className="trust-strip">
        <span>
          <IoShieldCheckmarkOutline /> Fuentes oficiales de Colombia
        </span>
        <span>
          <IoCalendarOutline /> Precios recientes e historia estacional
        </span>
        <span>
          <IoLeafOutline /> Sin registro, a tu alcance
        </span>
      </div>
      <HomeActions />
      <section className="home-coffee">
        <div className="coffee-symbol">
          <IoCafeOutline />
        </div>
        <div className="home-coffee-intro">
          <span className="eyebrow">HABLEMOS DE CAFÉ</span>
          <h2>El precio de tu café, claro.</h2>
          <p>Referencia FNC · Pergamino seco · Factor 94</p>
        </div>
        {coffee.data ? (
          <div className="home-coffee-price">
            <strong>
              {money(coffee.data.price)} <small>/ carga de 125 kg</small>
            </strong>
            <span>Referencia del {dateLabel(coffee.data.date, true)}</span>
          </div>
        ) : (
          <span className="muted">
            {coffee.loading
              ? "Consultando la referencia…"
              : "Consulta la disponibilidad de la referencia"}
          </span>
        )}
        <Link href="/coffee" className="button coffee-button">
          Ver precio del café <IoArrowForward />
        </Link>
      </section>
      <SectionTitle
        eyebrow={region || "DEL CAMPO COLOMBIANO"}
        title={
          role === "farmer"
            ? "¿Cómo están los precios?"
            : "Encuentra tu próxima compra"
        }
        href="/products"
        link="Todos los productos"
      />
      <p className="section-description">
        Precios mayoristas de referencia. Elige un producto para comparar
        mercados.
      </p>
      {catalog.loading ? (
        <LoadingCards />
      ) : catalog.error ? (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      ) : catalog.data?.products.length ? (
        <div className="product-grid">
          {catalog.data.products.slice(0, 4).map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <h3>No hay precios para este departamento</h3>
          <p>Selecciona Toda Colombia para ver los mercados disponibles.</p>
        </div>
      )}
      <section className="home-bottom">
        <div className="next-step">
          <span className="step-icon">
            <IoLocationOutline />
          </span>
          <div>
            <h3>El mismo producto, distintos precios.</h3>
            <p>
              Compara mercados y ten en cuenta el transporte antes de decidir.
            </p>
          </div>
          <Link href="/products" aria-label="Comparar mercados">
            <IoArrowForward />
          </Link>
        </div>
        <div className="source-note">
          <IoShieldCheckmarkOutline />
          <p>
            <strong>Información que puedes comprobar</strong>Cada precio tiene
            una fecha y una fuente. <Link href="/sources">Conócelas aquí.</Link>
          </p>
        </div>
      </section>
    </>
  );
}
