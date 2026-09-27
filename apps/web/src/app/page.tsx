"use client";
import { useEffect, useRef, useState } from "react";
import type { IconType } from "react-icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  IoArrowForward,
  IoLeafOutline,
  IoBasketOutline,
  IoStorefrontOutline,
  IoFlaskOutline,
  IoDocumentTextOutline,
} from "react-icons/io5";
import {
  ProductCard,
  ErrorState,
  LoadingCards,
  SectionTitle,
} from "@/components/marketplace/Shared";
import { useCatalogPage } from "@/components/marketplace/useCatalogPage";
import { SearchBox } from "@/components/ui/SearchBox";
import { useFarm } from "@/components/planning/FarmContext";
import { photoFor } from "@/lib/images";
import { catalogHref, catalogIdentity } from "@/lib/catalog-display";
import sourceStyles from "./source-links.module.css";

function SectionPhoto({ src, icon: Icon }: { src: string; icon: IconType }) {
  const image = useRef<HTMLImageElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    // A cached image failure can occur before React attaches onError.
    if (image.current?.complete && !image.current.naturalWidth) setFailed(true);
  }, [src]);
  return failed ? (
    <span className="home-section-placeholder" aria-hidden="true"><Icon /></span>
  ) : <img ref={image} src={src} alt="" onError={() => setFailed(true)} />;
}

export default function Home() {
  const { farm } = useFarm(),
    router = useRouter();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  const catalog = useCatalogPage('{"limit":4}');
  const suggestions = useCatalogPage(debouncedSearch.trim()
    ? JSON.stringify({ q: debouncedSearch, limit: 24 }) : null);
  const suggestionProducts = search === debouncedSearch
    ? suggestions.data?.products || [] : [];
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
          filterOptions={false}
          options={suggestionProducts.map((p) => ({
            id: catalogIdentity(p),
            label: p.name,
            detail: [p.category, p.currency, p.basis].filter(Boolean).join(" · "),
          }))}
          onSelect={(option) => {
            const product = suggestionProducts.find((p) => catalogIdentity(p) === option.id);
            if (product) router.push(catalogHref(product, "/products?q=" + encodeURIComponent(search)));
          }}
          onSubmit={() =>
            router.push("/products?q=" + encodeURIComponent(search))
          }
        />
        {search === debouncedSearch && suggestions.error && (
          <ErrorState message={suggestions.error} retry={suggestions.retry} />
        )}
      </div>
      <div className="home-sections">
        {sections.map(({ href, label, detail, photo, icon: Icon }) => (
          <Link key={href} href={href} className="home-section">
            <SectionPhoto src={photo} icon={Icon} />
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
          <p>Explora el clima y los suelos. Compara costos y rentabilidad.</p>
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
            <ProductCard key={catalogIdentity(p)} product={p} />
          ))}
        </div>
      )}
      <section className={sourceStyles.sourceCard} aria-label="Fuentes de la información">
        <IoDocumentTextOutline aria-hidden="true" />
        <div>
          <h2>Consulta de dónde viene cada dato</h2>
          <p>Junto a los precios, mapas y pronósticos encontrarás su fuente, fecha y documento original.</p>
          <Link href="/sources">Conocer las fuentes <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </>
  );
}
