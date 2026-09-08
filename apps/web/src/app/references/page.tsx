"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { dateLabel } from "@/lib/market-types";
import { officialMoney, type OfficialPrice } from "@/lib/official-types";
type Catalog = {
  rows: OfficialPrice[];
  total: number;
  page: number;
  options: { categories: string[]; publishers: string[]; currencies: string[] };
};
export default function References() {
  const [q, setQ] = useState(""),
    [category, setCategory] = useState(""),
    [publisher, setPublisher] = useState(""),
    [currency, setCurrency] = useState(""),
    [page, setPage] = useState(0);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ(p.get("q") || "");
    setCategory(p.get("category") || "");
  }, []);
  const { data, loading, error, retry } = useData<Catalog>(
    "/api/references?" +
      new URLSearchParams({
        q,
        category,
        publisher,
        currency,
        page: String(page),
      }),
  );
  const [options, setOptions] = useState<Catalog["options"]>({
    categories: [],
    publishers: [],
    currencies: [],
  });
  useEffect(() => {
    if (data) setOptions(data.options);
  }, [data]);
  return (
    <>
      <Link href="/products" className="back-link">
        ← Productos
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            ENTIDADES OFICIALES Y FUENTES PRIMARIAS
          </span>
          <h1>Otras referencias de precios</h1>
          <p>
            Café, cacao, flores, bananos, aceites, azúcar y carnes. Cada
            referencia conserva su mercado, moneda y unidad.
          </p>
        </div>
      </div>
      <section className="panel">
        <p>
          Consulta el tipo de precio antes de comparar: una referencia
          internacional, un precio de compra, una cotización mayorista y una
          base reglamentaria corresponden a operaciones distintas.
        </p>
        <div className="price-filter-grid">
          <label className="form-field">
            Buscar referencia
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
              placeholder="Café, cacao, rosas…"
            />
          </label>
          <label className="form-field">
            Categoría
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Todas</option>
              {options.categories.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Entidad
            <select
              value={publisher}
              onChange={(e) => {
                setPublisher(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Todas</option>
              {options.publishers.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Moneda
            <select
              value={currency}
              onChange={(e) => {
                setCurrency(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Todas</option>
              {options.currencies.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        </div>
      </section>
      <AppliedFilters
        items={[
          { label: "Búsqueda", value: q },
          { label: "Categoría", value: category || "Todas" },
          { label: "Entidad", value: publisher || "Todas" },
          {
            label: "Moneda",
            value: currency || "Moneda original de cada fuente",
          },
          { label: "Fecha", value: "Último dato de cada serie" },
        ]}
      />
      {loading ? (
        <p role="status">Consultando referencias oficiales…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <p className="results-label">
              {data.total} referencias · Página {page + 1}
            </p>
            <div className="input-grid">
              {data.rows.map((r) => (
                <article
                  className="panel input-card official-reference"
                  key={r.quote_key}
                >
                  <span className="eyebrow">
                    {r.publisher} · {r.category}
                  </span>
                  <h2>
                    <Link href={"/references/" + r.quote_key}>
                      {r.product_name}
                    </Link>
                  </h2>
                  <p>{r.market}</p>
                  <strong className="input-price">
                    {r.min_price !== null && r.max_price !== null
                      ? `${officialMoney(r.min_price, r.currency)} – ${officialMoney(r.max_price, r.currency)}`
                      : officialMoney(r.price, r.currency)}
                  </strong>
                  <p>
                    Por {r.unit} · {dateLabel(r.observed_on)}
                  </p>
                  <p className="reference-basis">{r.basis}</p>
                  <div className="detail-actions">
                    <Link href={"/references/" + r.quote_key}>
                      Ver historial →
                    </Link>
                    <EvidenceLink
                      id={r.document_id}
                      page={r.source_page}
                      locator={r.source_locator}
                    >
                      Consultar fuente
                    </EvidenceLink>
                  </div>
                </article>
              ))}
            </div>
            {!data.total && (
              <p className="empty-state">
                No hay referencias con estos filtros.
              </p>
            )}
            <div className="load-more">
              <button
                className="button secondary"
                disabled={!page}
                onClick={() => setPage((p) => p - 1)}
              >
                ← Anterior
              </button>
              <button
                className="button secondary"
                disabled={(page + 1) * 48 >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Siguiente →
              </button>
            </div>
          </>
        )
      )}
    </>
  );
}
