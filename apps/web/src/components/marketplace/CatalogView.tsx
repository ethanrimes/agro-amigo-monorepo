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
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import type { UnifiedCatalog } from "@/lib/catalog-types";
import {
  catalogCurrency,
  catalogHref,
  catalogIdentity,
  catalogMatches,
  catalogReturnTo,
  catalogSavedKey,
  catalogUnit,
} from "@/lib/catalog-display";
import styles from "./catalog.module.css";

export function CatalogView({ savedOnly = false }: { savedOnly?: boolean }) {
  const { region, saved, setRegion } = usePreferences(),
    router = useRouter();
  const { data, loading, error, retry } = useData<UnifiedCatalog>(
    "/api/catalog?region=" + encodeURIComponent(region),
  );
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState("Todos"),
    [currency, setCurrency] = useState(""),
    [limit, setLimit] = useState(24),
    [filtersReady, setFiltersReady] = useState(false);
  useEffect(() => {
    const restore = () => {
      const params = new URLSearchParams(window.location.search);
      setQuery(params.get("q") || "");
      setCategory(params.get("category") || "Todos");
      setCurrency(params.get("currency") || "");
      setFiltersReady(true);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  const returnTo = catalogReturnTo(
    savedOnly ? "/saved" : "/products",
    query,
    category,
    currency,
  );
  useEffect(() => {
    if (
      filtersReady &&
      window.location.pathname + window.location.search !== returnTo
    )
      window.history.replaceState(window.history.state, "", returnTo);
  }, [filtersReady, returnTo]);
  useEffect(() => setLimit(24), [query, category, currency, region]);

  const rows = data?.products || [];
  const candidates = rows.filter(
    (product) =>
      (!savedOnly || saved.includes(catalogSavedKey(product))) &&
      (category === "Todos" || product.category === category) &&
      (!currency || catalogCurrency(product) === currency),
  );
  const products = candidates.filter((product) =>
    catalogMatches(product, query),
  );
  const categories = [
    ...new Set([
      ...rows.map((p) => p.category),
      ...(category !== "Todos" ? [category] : []),
    ]),
  ].sort((a, b) => a.localeCompare(b, "es"));
  const currencies = [
    ...new Set([...rows.map(catalogCurrency), ...(currency ? [currency] : [])]),
  ].sort();
  const mapProduct =
    products.find(
      (p) => p.map_supported !== false && p.id === "aguacate-hass",
    ) || products.find((p) => p.map_supported !== false);

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
              : "Busca tu producto o variedad y consulta sus precios."}
          </p>
        </div>
        {!savedOnly && mapProduct && (
          <MapButton
            kind="product"
            id={mapProduct.id}
            filters={{
              region,
              series: mapProduct.series,
              presentation: mapProduct.presentation,
              units: mapProduct.units,
            }}
          />
        )}
      </div>
      <div className={styles.controls}>
        <div className={styles.search}>
          <span>Producto o variedad</span>
          <SearchBox
            label="Buscar producto"
            placeholder="Café arábica, cacao, rosas, tomate…"
            value={query}
            onChange={setQuery}
            filterOptions={false}
            options={products.map((p) => ({
              id: catalogIdentity(p),
              label: p.name,
              detail: `${p.category} · ${catalogCurrency(p)} / ${catalogUnit(p)}`,
            }))}
            onSelect={(option) => {
              const product = products.find(
                (p) => catalogIdentity(p) === option.id,
              );
              if (product) {
                setQuery(query);
                router.push(catalogHref(product, returnTo));
              }
            }}
          />
        </div>
        <label className={`${styles.field} ${styles.department}`}>
          <span>Departamento</span>
          <select
            aria-label="Departamento"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
          >
            <option value="">Sin filtro de departamento</option>
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
        <label className={styles.field}>
          <span>Categoría</span>
          <select
            aria-label="Categoría"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="Todos">Todas</option>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span>Moneda</span>
          <select
            aria-label="Moneda"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="">Todas</option>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c === "COP"
                  ? "COP · pesos"
                  : c === "USD"
                    ? "USD · dólares"
                    : c}
              </option>
            ))}
          </select>
        </label>
      </div>
      {data?.filters?.excluded_nonregional_reason && (
        <p className={styles.regionNote}>
          {data.filters.excluded_nonregional_reason}
        </p>
      )}
      <div className={styles.activeFilters}>
        <AppliedFilters
          items={[
            {
              label: "Departamento",
              value: region || "Sin filtro",
              clear: region ? () => setRegion("") : undefined,
            },
            {
              label: "Categoría",
              value: category === "Todos" ? "Todas" : category,
              clear:
                category !== "Todos" ? () => setCategory("Todos") : undefined,
            },
            {
              label: "Moneda",
              value: currency || "Todas",
              clear: currency ? () => setCurrency("") : undefined,
            },
            {
              label: "Búsqueda",
              value: query || "Todos los productos",
              clear: query ? () => setQuery("") : undefined,
            },
          ]}
        />
      </div>
      {loading ? (
        <LoadingCards />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>
              {products.length} resultados
              {region ? " en " + region : ""}
            </span>
            <Link href={savedOnly ? "/products" : "/saved"}>
              {savedOnly ? "Ver todos los productos" : "Mis guardados"}
            </Link>
          </div>
          {products.length ? (
            <div className="product-grid">
              {products.slice(0, limit).map((p) => (
                <ProductCard
                  key={catalogIdentity(p)}
                  product={p}
                  detailReturnTo={returnTo}
                />
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
                  : "Prueba otro nombre o ajusta los filtros de departamento, categoría y moneda."}
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
        Cada precio conserva su moneda, unidad y fecha. Abre un producto para
        consultar su historial y su fuente.
      </Notice>
    </>
  );
}
