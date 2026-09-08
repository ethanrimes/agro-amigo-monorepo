"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { IoHeartOutline } from "react-icons/io5";
import { usePreferences } from "./Preferences";
import { useData } from "./useData";
import { ProductCard, ErrorState, LoadingCards, Notice } from "./Shared";
import { SearchBox } from "@/components/ui/SearchBox";
import { MapButton } from "@/components/explore/ColombiaMap";
import { fold } from "@/lib/planning-math";
import type { Catalog } from "@/lib/market-types";
export function CatalogView({ savedOnly = false }: { savedOnly?: boolean }) {
  const { region, saved, setRegion } = usePreferences(),
    router = useRouter();
  const { data, loading, error, retry } = useData<Catalog>(
    "/api/catalog?region=" + encodeURIComponent(region),
  );
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState("Todos"),
    [limit, setLimit] = useState(24);
  useEffect(
    () => setQuery(new URLSearchParams(window.location.search).get("q") || ""),
    [],
  );
  useEffect(() => setLimit(24), [query, category, region]);
  const candidates = (data?.products || []).filter(
    (p) =>
      (!savedOnly || saved.includes(p.id)) &&
      (category === "Todos" || p.category === category),
  );
  const products = candidates.filter((p) => fold(p.name).includes(fold(query)));
  const categories = [
    "Todos",
    ...new Set((data?.products || []).map((p) => p.category)),
  ];
  return (
    <>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">
            {savedOnly ? "TUS CONSULTAS A MANO" : "DEL CAMPO COLOMBIANO"}
          </span>
          <h1>{savedOnly ? "Mis guardados" : "Productos agrícolas"}</h1>
          <p>
            {savedOnly
              ? "Los productos que te interesan, en este dispositivo."
              : "Encuentra tu producto. Consulta precios y abastecimiento."}
          </p>
        </div>
        {!savedOnly && (
          <MapButton
            kind="product"
            id={
              products.find((p) => p.id === "aguacate-hass")?.id ||
              products[0]?.id
            }
          />
        )}
      </div>
      <div className="catalog-controls">
        <SearchBox
          label="Buscar producto"
          placeholder="Café, papa, aguacate…"
          value={query}
          onChange={setQuery}
          options={candidates.map((p) => ({
            id: p.id,
            label: p.name,
            detail: p.category,
          }))}
          onSelect={(p) => router.push("/product/" + p.id)}
        />
        <label className="region-field">
          <span>Departamento</span>
          <select
            aria-label="Departamento"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            <option value="">Toda Colombia</option>
            {[
              ...new Set([
                ...(data?.regions || []),
                ...(region ? [region] : []),
              ]),
            ]
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
            aria-pressed={category === c}
            className={category === c ? "active" : ""}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </div>
      {loading ? (
        <LoadingCards />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>
              {products.length} productos{" "}
              {region ? "en " + region : "en Colombia"}
            </span>
            <Link href={savedOnly ? "/products" : "/saved"}>
              {savedOnly ? "Ver todos los productos" : "Mis guardados"}
            </Link>
          </div>
          {products.length ? (
            <div className="product-grid">
              {products.slice(0, limit).map((p) => (
                <ProductCard key={`${p.id}:${p.unit}:${p.source}`} product={p} />
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <IoHeartOutline />
              <h2>
                {savedOnly
                  ? "Guarda lo que te interesa"
                  : "No encontramos productos"}
              </h2>
              <p>
                {savedOnly
                  ? "Toca el corazón de un producto para encontrarlo aquí."
                  : "Prueba otro nombre o departamento."}
              </p>
              <Link className="button primary" href="/products">
                Explorar productos
              </Link>
            </div>
          )}
          {products.length > limit && (
            <div className="load-more">
              <button
                className="button secondary"
                onClick={() => setLimit((v) => v + 24)}
              >
                Ver más productos ({products.length - limit})
              </button>
            </div>
          )}
        </>
      )}
      <Notice>
        DANE SIPSA: promedios mayoristas mensuales. Café: referencia diaria FNC
        por carga de 125 kg. Cada detalle conserva su fecha, unidad y fuente.
      </Notice>
    </>
  );
}
