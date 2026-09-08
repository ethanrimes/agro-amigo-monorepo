"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { dateLabel, number } from "@/lib/market-types";
const titles: Record<string, string> = {
  summary: "Resumen de insumos",
  electricity: "Energía eléctrica",
  wholesale: "Resumen mayorista mensual",
};
type Data = {
  rows: {
    name: string;
    category: string;
    document_id: string;
    source_locator: string;
    details: Record<string, unknown>;
  }[];
  total: number;
  dates: string[];
  categories: string[];
  date: string | null;
  kind: string;
};
export default function DataReferences() {
  const [kind, setKind] = useState("summary"),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState(""),
    [date, setDate] = useState(""),
    [page, setPage] = useState(0);
  useEffect(() => {
    const k = new URLSearchParams(window.location.search).get("kind");
    if (k && titles[k]) setKind(k);
  }, []);
  const { data, loading, error, retry } = useData<Data>(
    "/api/data-references?" +
      new URLSearchParams({
        kind,
        q: query,
        category,
        date,
        page: String(page),
      }),
  );
  const [previous, setPrevious] = useState<Data | null>(null);
  useEffect(() => {
    if (data) setPrevious(data);
  }, [data]);
  const meta = data || previous;
  return (
    <>
      <Link
        className="back-link"
        href={kind === "wholesale" ? "/products" : "/insumos"}
      >
        ← {kind === "wholesale" ? "Productos" : "Insumos"}
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">DANE · ANEXOS COMPLEMENTARIOS</span>
          <h1>{titles[kind]}</h1>
          <p>
            {kind === "electricity"
              ? "Tarifas por proveedor, estrato y mes; conserva subsidios y contribuciones de la publicación."
              : kind === "summary"
                ? "Mínimos y máximos de los promedios municipales, y número de municipios con variaciones."
                : "Precios y variaciones por producto y ciudad del anexo mensual."}
          </p>
        </div>
      </div>
      <section className="panel price-filter-grid">
        <label className="form-field">
          Datos
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setDate("");
              setCategory("");
              setPage(0);
            }}
          >
            {Object.entries(titles).map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          Mes
          <select
            value={data?.date || date}
            onChange={(e) => {
              setDate(e.target.value);
              setPage(0);
            }}
          >
            {meta?.dates.map((d) => (
              <option key={d} value={d}>
                {dateLabel(d)}
              </option>
            ))}
          </select>
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
            {meta?.categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="form-field">
          Buscar
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
      </section>
      <AppliedFilters
        items={[
          { label: "Datos", value: titles[kind] },
          { label: "Mes", value: data?.date ? dateLabel(data.date) : date },
          { label: "Categoría", value: category || "Todas" },
          { label: "Búsqueda", value: query },
        ]}
      />
      {loading ? (
        <p role="status">Consultando anexo…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <p className="results-label">{data.total} registros</p>
            <div className="input-grid">
              {data.rows.map((r) => (
                <article
                  className="panel"
                  key={r.document_id + r.source_locator}
                >
                  <span className="eyebrow">{r.category}</span>
                  <h2>{r.name}</h2>
                  <dl className="reference-metadata">
                    {Object.entries(r.details)
                      .filter(([, v]) => v !== null)
                      .map(([key, v]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>
                            {typeof v === "number"
                              ? key === "Subsidio" || key === "Contribución"
                                ? number(v * 100) + " %"
                                : number(v)
                              : String(v)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                  <EvidenceLink id={r.document_id} locator={r.source_locator}>
                    Consultar Excel original
                  </EvidenceLink>
                </article>
              ))}
            </div>
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
                disabled={(page + 1) * 60 >= data.total}
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
