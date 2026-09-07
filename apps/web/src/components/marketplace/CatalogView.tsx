"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  IoSearchOutline,
  IoHeartOutline,
  IoClose,
  IoCafeOutline,
  IoArrowForward,
} from "react-icons/io5";
import { usePreferences } from "./Preferences";
import { useData } from "./useData";
import {
  ProductCard,
  ErrorState,
  LoadingCards,
  RoleSwitch,
  Notice,
} from "./Shared";
import type { Catalog } from "@/lib/market-types";
const normalize = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
export function CatalogView({ savedOnly = false }: { savedOnly?: boolean }) {
  const { region, saved, setRegion } = usePreferences();
  const { data, loading, error, retry } = useData<Catalog>(
    "/api/catalog?region=" + encodeURIComponent(region),
  );
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Todos");
  const [limit, setLimit] = useState(24);
  useEffect(() => {
    setQuery(new URLSearchParams(window.location.search).get("q") || "");
  }, []);
  useEffect(() => {
    setLimit(24);
  }, [query, category, region]);
  const categories = useMemo(
    () => [
      "Todos",
      ...Array.from(new Set((data?.products || []).map((p) => p.category))),
    ],
    [data],
  );
  const products = (data?.products || []).filter(
    (p) =>
      (!savedOnly || saved.includes(p.id)) &&
      (category === "Todos" || p.category === category) &&
      normalize(p.name).includes(normalize(query)),
  );
  const showCoffee =
    category === "Todos" &&
    (!query || normalize("café pergamino seco").includes(normalize(query))) &&
    (!savedOnly || saved.includes("cafe-pergamino-seco"));
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            {savedOnly
              ? "A UN PASO DE LO QUE CULTIVAS"
              : "INFORMACIÓN PARA DECIDIR"}
          </span>
          <h1>{savedOnly ? "Mis productos" : "Precios del campo"}</h1>
          <p>
            {savedOnly
              ? "Tus favoritos, reunidos en un solo lugar."
              : "Busca tu producto y compara su precio entre mercados."}
          </p>
        </div>
        <RoleSwitch />
      </div>
      {!savedOnly && (
        <div className="panel daily-prompt">
          <div>
            <strong>¿Vas a negociar esta semana?</strong>
            <p>Consulta también el último boletín diario de DANE.</p>
          </div>
          <Link className="button secondary" href="/daily">
            Ver precios diarios →
          </Link>
        </div>
      )}
      <div className="catalog-controls">
        <div className="search-field">
          <IoSearchOutline />
          <input
            placeholder="Buscar producto…"
            aria-label="Buscar producto"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button aria-label="Borrar búsqueda" onClick={() => setQuery("")}>
              <IoClose />
            </button>
          )}
        </div>
        <label className="region-field">
          <span>Departamento</span>
          <select
            aria-label="Departamento"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            <option value="">Toda Colombia</option>
            {Array.from(
              new Set([...(data?.regions || []), ...(region ? [region] : [])]),
            )
              .sort()
              .map((r) => (
                <option key={r}>{r}</option>
              ))}
          </select>
        </label>
      </div>
      <div className="category-filters" aria-label="Filtrar por categoría">
        {categories.map((c) => (
          <button
            key={c}
            className={c === category ? "active" : ""}
            aria-pressed={c === category}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>
      {showCoffee && (
        <Link href="/coffee" className="coffee-search-result">
          <IoCafeOutline />
          <div>
            <strong>Café pergamino seco</strong>
            <span>Referencia FNC, precios regionales y calculadora</span>
          </div>
          <IoArrowForward />
        </Link>
      )}
      {loading ? (
        <LoadingCards />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>
              {products.length + (showCoffee ? 1 : 0)} productos{" "}
              {region ? "en " + region : "en Colombia"}
            </span>
            <span>DANE · SIPSA · COP por kg</span>
          </div>
          {products.length ? (
            <div className="product-grid">
              {products.slice(0, limit).map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          ) : showCoffee ? null : (
            <div className="empty-state">
              <IoHeartOutline />
              <h2>
                {savedOnly
                  ? "Guarda lo que te interesa"
                  : "No encontramos productos"}
              </h2>
              <p>
                {savedOnly
                  ? "Toca el corazón de un producto para encontrarlo aquí. Se guarda en este dispositivo."
                  : "Prueba otro nombre o selecciona Toda Colombia."}
              </p>
              <Link className="button primary" href="/products">
                Explorar productos <IoArrowForward />
              </Link>
            </div>
          )}
          {products.length > limit && (
            <div className="load-more">
              <button
                className="button secondary"
                onClick={() => setLimit((x) => x + 24)}
              >
                Ver más productos ({products.length - limit})
              </button>
            </div>
          )}
        </>
      )}
      <Notice>
        Los valores son promedios mensuales de venta mayorista publicados por
        DANE, no precios de compra en finca. El precio de una negociación
        depende de la calidad, el volumen y el transporte.
      </Notice>
    </>
  );
}
