"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { IoHeartOutline } from "react-icons/io5";
import { usePreferences } from "./Preferences";
import { useCatalogPage } from "./useCatalogPage";
import { ProductCard, ErrorState, LoadingCards, Notice } from "./Shared";
import { SearchBox } from "@/components/ui/SearchBox";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { HierarchicalCategorySelect } from "@/components/ui/HierarchicalCategorySelect";
import { MapButton } from "@/components/explore/ColombiaMap";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import type { CatalogPage, CatalogProduct } from "@/lib/catalog-types";
import { categoryKey, categoryLabels, departmentLabel, departmentLabels } from "@/lib/filter-labels";
import {
  catalogHref,
  catalogIdentity,
  catalogReturnTo,
  catalogSuggestionDetail,
} from "@/lib/catalog-display";
import styles from "./catalog.module.css";

export function CatalogView({ savedOnly = false }: { savedOnly?: boolean }) {
  const { region, saved, setRegion, ready } = usePreferences(),
    router = useRouter();
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState("Todos"),
    [currency, setCurrency] = useState(""),
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
  const [search, setSearch] = useState("");
  const returnTo = catalogReturnTo(
    savedOnly ? "/saved" : "/products",
    query,
    category,
    currency,
  );
  // Keep the address in step with the debounced query. WebKit limits history
  // writes, so updating it on every keystroke can crash an ordinary search.
  useEffect(() => {
    if (
      filtersReady &&
      query === search &&
      window.location.pathname + window.location.search !== returnTo
    )
      window.history.replaceState(null, "", returnTo);
  }, [filtersReady, returnTo, query, search]);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const criteria = { region, q: search, category, currency, ...(savedOnly ? { saved } : {}) };
  const criteriaKey = JSON.stringify(criteria);
  const [position, setPosition] = useState({ key: "", offset: 0 });
  const offset = position.key === criteriaKey ? position.offset : 0;
  const { data, loading: fetching, error, retry } = useCatalogPage(
    ready && filtersReady ? JSON.stringify({ ...criteria, offset, limit: 24 }) : null,
  );
  const [loaded, setLoaded] = useState<{ key: string; products: CatalogProduct[]; metadata: CatalogPage | null }>({ key: "", products: [], metadata: null });
  useEffect(() => {
    if (!data) return;
    setLoaded((old) => ({
      key: criteriaKey,
      products: [...new Map([
        ...(data.pagination.offset > 0 && old.key === criteriaKey ? old.products : []),
        ...data.products,
      ].map((product) => [catalogIdentity(product), product])).values()],
      metadata: data,
    }));
  }, [data, criteriaKey]);
  const loading = fetching || query !== search || !ready || !filtersReady;
  const metadata = data || (loaded.key === criteriaKey ? loaded.metadata : null);
  const products = loaded.key === criteriaKey ? loaded.products : data?.products || [];
  const total = metadata?.total || 0;
  const categories = categoryLabels(metadata?.categories || []);
  const selectedCategory = categories.find((label) => categoryKey(label) === categoryKey(category)) || category;
  const currencies = [...new Set([
    ...(metadata?.currencies || []), ...(currency ? [currency] : []),
  ])].sort();
  const mapProduct = metadata?.map_product;
  const addingPage = offset > 0 && loaded.key === criteriaKey && products.length > 0;

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
        {!savedOnly && (
          <span aria-hidden={!loading && !mapProduct} style={{ visibility: !loading && !mapProduct ? "hidden" : undefined }}>
            <MapButton
              kind="product"
              id={mapProduct?.id}
              disabled={loading || !mapProduct}
              filters={{
                region,
                category: selectedCategory === "Todos" ? "" : selectedCategory,
                history: mapProduct?.series === "city" ? "all" : "recent",
                series: mapProduct?.series,
                presentation: mapProduct?.presentation,
                units: mapProduct?.units,
              }}
            />
          </span>
        )}
      </div>
      {!savedOnly && (
        <p><Link className="button secondary" href="/daily">Consultar boletines diarios por fecha →</Link></p>
      )}
      <div className={styles.controls}>
        <div className={styles.search}>
          <span>Producto, variedad o mercado</span>
          <SearchBox
            label="Buscar producto, variedad o mercado"
            placeholder="Sardinas Armenia, café, cacao…"
            value={query}
            onChange={setQuery}
            filterOptions={false}
            loading={loading}
            error={Boolean(error)}
            options={products.map((p) => ({
              id: catalogIdentity(p),
              label: p.name,
              detail: catalogSuggestionDetail(p),
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
        <SearchableSelect
          className={`${styles.field} ${styles.department}`}
          label="Departamento"
          value={departmentLabel(region)}
          onChange={setRegion}
          options={departmentLabels([...(metadata?.regions || []), ...(region ? [region] : [])]).map((name) => ({ id: name, label: name }))}
          emptyLabel="Sin filtro de departamento"
          loading={loading && !metadata}
        />
        <HierarchicalCategorySelect
          className={styles.field}
          value={selectedCategory === "Todos" ? "" : selectedCategory}
          onChange={(value) => setCategory(value || "Todos")}
          paths={categories}
          loading={loading && !metadata}
        />
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
      {metadata?.filters?.excluded_nonregional_reason && (
        <p className={styles.regionNote}>
          El filtro de departamento incluye solo ubicaciones verificadas. Si quieres, quítalo para consultar todas las referencias.
        </p>
      )}
      <div className={styles.activeFilters}>
        <AppliedFilters
          items={[
            {
              label: "Departamento",
              value: departmentLabel(region) || "Sin filtro",
              clear: region ? () => setRegion("") : undefined,
            },
            {
              label: "Categoría",
              value: category === "Todos" ? "Todas" : selectedCategory,
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
      {loading && !addingPage ? (
        <LoadingCards />
      ) : error && !addingPage ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        <>
          <div className="results-label">
            <span>
              {total} resultados
              {region ? " en " + region : ""}
            </span>
            <Link href={savedOnly ? "/products" : "/saved"}>
              {savedOnly ? "Ver todos los productos" : "Mis guardados"}
            </Link>
          </div>
          {products.length ? (
            <div className="product-grid">
              {products.map((p) => (
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
          {metadata?.pagination.has_more && (
            <div className="load-more">
              <button
                className="button secondary"
                disabled={loading}
                onClick={() => error ? retry() : setPosition({ key: criteriaKey, offset: metadata.pagination.offset + metadata.pagination.limit })}
              >
                {loading ? "Cargando resultados…" : error ? "Reintentar cargar más" : `Ver más resultados (${Math.max(0, total - products.length)})`}
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
