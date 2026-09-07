"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  IoArrowForward,
  IoLeafOutline,
  IoBasketOutline,
  IoStorefrontOutline,
  IoFlaskOutline,
} from "react-icons/io5";
import {
  ProductCard,
  ErrorState,
  LoadingCards,
  SectionTitle,
} from "@/components/marketplace/Shared";
import { useData } from "@/components/marketplace/useData";
import { SearchBox } from "@/components/ui/SearchBox";
import { useFarm } from "@/components/planning/FarmContext";
import { photoFor } from "@/lib/images";
import type { Catalog } from "@/lib/market-types";
export default function Home() {
  const { farm } = useFarm(),
    router = useRouter();
  const [search, setSearch] = useState("");
  const catalog = useData<Catalog>("/api/catalog");
  const sections = [
    {
      href: "/products",
      label: "Productos",
      detail: "Precios y abastecimiento",
      photo: "/images/produce.jpg",
      icon: IoBasketOutline,
    },
    {
      href: "/markets",
      label: "Mercados",
      detail: "Encuentra dónde comparar",
      photo: photoFor("Paloquemao", "", "market").src,
      icon: IoStorefrontOutline,
    },
    {
      href: "/insumos",
      label: "Insumos",
      detail: "Lo que necesita tu cultivo",
      photo: photoFor("Fertilizante", "", "input").src,
      icon: IoFlaskOutline,
    },
  ];
  return (
    <>
      <div className="welcome-row">
        <span className="eyebrow">BIENVENIDO A AGROAMIGO</span>
      </div>
      <section className="home-hero">
        <img
          src="/images/farm.jpg"
          alt="Paisaje agrícola, imagen ilustrativa"
          fetchPriority="high"
        />
        <div className="home-hero-copy">
          <span>INFORMACIÓN PARA TU DÍA A DÍA</span>
          <h1>El campo, a tu alcance.</h1>
          <p>Productos, mercados e insumos. Datos claros para decidir mejor.</p>
        </div>
      </section>
      <div className="home-search">
        <SearchBox
          label="Buscar un producto"
          placeholder="¿Qué producto buscas? Café, papa, aguacate…"
          value={search}
          onChange={setSearch}
          options={(catalog.data?.products || []).map((p) => ({
            id: p.id,
            label: p.name,
            detail: p.category,
          }))}
          onSelect={(p) => router.push("/product/" + p.id)}
          onSubmit={() =>
            router.push("/products?q=" + encodeURIComponent(search))
          }
        />
      </div>
      <div className="home-sections">
        {sections.map(({ href, label, detail, photo, icon: Icon }) => (
          <Link key={href} href={href} className="home-section">
            <img src={photo} alt="" />
            <div>
              <Icon />
              <h2>{label}</h2>
              <p>{detail}</p>
              <span>
                Explorar <IoArrowForward />
              </span>
            </div>
          </Link>
        ))}
      </div>
      <Link href="/farm" className="farm-invitation">
        <span className="farm-invitation-icon">
          <IoLeafOutline />
        </span>
        <div>
          <h2>
            {farm.municipalityId ? farm.name : "Tu finca, tus decisiones"}
          </h2>
          <p>Organiza la semana. Explora cultivos y haz tus cuentas.</p>
        </div>
        <IoArrowForward />
      </Link>
      <SectionTitle
        title="Productos para consultar"
        href="/products"
        link="Ver todos"
      />
      {catalog.loading ? (
        <LoadingCards />
      ) : catalog.error ? (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      ) : (
        <div className="product-grid">
          {catalog.data?.products.slice(0, 4).map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
      <div className="home-source">
        <strong>Información que puedes comprobar.</strong>
        <span>
          Abre la fuente junto a cada dato para consultar el documento.
        </span>
        <Link href="/sources">Conocer las fuentes →</Link>
      </div>
    </>
  );
}
