"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { dateLabel, number, unitLabel } from "@/lib/market-types";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { HierarchicalCategorySelect } from "@/components/ui/HierarchicalCategorySelect";
import { normalizeLabel } from "@/lib/label-normalization";
const titles: Record<string, string> = {
  summary: "Resumen de insumos",
  electricity: "Energía eléctrica",
  wholesale: "Resumen mayorista mensual",
};
// Published tariffs and percentages retain decimals omitted by the compact
// one-decimal summary formatter.
const sourceDecimal = new Intl.NumberFormat("es-CO", {
  maximumFractionDigits: 4,
});
const supportPercentage = (key: string) => /^(subsidio|subsidios|contribucion|contribuciones)$/.test(
  key.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase(),
);
type Data = {
  rows: {
    name: string;
    category: string;
    document_id: string;
    source_locator: string;
    observed_on: string;
    details: Record<string, unknown>;
  }[];
  total: number;
  dates: string[];
  categories: string[];
  date: string | null;
  kind: string;
};
type ReferenceRow = Data["rows"][number];
const recordId = (row: ReferenceRow) => row.document_id + ":" + row.source_locator;
const recordLabel = (row: ReferenceRow) => [
  row.name,
  row.details.Estrato !== undefined ? `Estrato ${row.details.Estrato}` : "",
  row.details.Ciudad,
  row.details.Presentación,
  row.details.Unidad,
].filter(Boolean).join(" · ");
export default function DataReferences() {
  const [kind, setKind] = useState("summary"),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState(""),
    [date, setDate] = useState(""),
    [page, setPage] = useState(0),
    [selectedRecord, setSelectedRecord] = useState("");
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
  useEffect(() => { setSelectedRecord(""); }, [kind, query, category, date, page, data?.date]);
  const chosen = data?.rows.find((row) => recordId(row) === selectedRecord);
  const visibleRows = data?.rows.slice(0, 6) || [];
  if (chosen && !visibleRows.some((row) => recordId(row) === selectedRecord)) visibleRows.push(chosen);
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
        <SearchableSelect
          label="Mes"
          allowClear={false}
          value={date || data?.date || ""}
          options={(meta?.dates || []).map((value) => ({ id: value, label: dateLabel(value), detail: value }))}
          onChange={(value) => { setDate(value); setPage(0); }}
          placeholder="Busca mes o año"
          emptyLabel="Último mes disponible"
          loading={loading && !meta}
          error={Boolean(error) && !meta}
        />
        <HierarchicalCategorySelect
          value={category}
          paths={meta?.categories || []}
          onChange={(value) => { setCategory(value); setPage(0); }}
        />
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
          { label: "Categoría", value: category ? normalizeLabel(category, "category") : "Todas" },
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
            {data.total > 0 && <p className="help-text">
              Página {page + 1} de {Math.ceil(data.total / 60)} · registros {page * 60 + 1}–{page * 60 + data.rows.length} de {data.total}.
              {data.rows.length > 6 && " Se muestran seis registros y el registro elegido. Busca en esta página o cambia de página para consultar los demás."}
            </p>}
            {data.rows.length > 6 && <SearchableSelect
              label="Consultar un registro de esta página"
              value={selectedRecord}
              options={data.rows.map((row) => ({
                id: recordId(row),
                label: recordLabel(row),
                detail: dateLabel(row.observed_on) + " · " + normalizeLabel(row.category, "category"),
              }))}
              onChange={setSelectedRecord}
              placeholder="Busca producto, proveedor, estrato o ciudad"
              emptyLabel="Elige un registro para verlo junto a los seis primeros"
            />}
            <div className="input-grid">
              {visibleRows.map((r) => (
                <article
                  className="panel"
                  key={r.document_id + r.source_locator}
                >
                  <span className="eyebrow">{normalizeLabel(r.category, "category")}</span>
                  <h2>{r.name}</h2>
                  <dl className="reference-metadata">
                    {Object.entries(r.details)
                      .filter(([, v]) => v !== null)
                      .map(([key, v]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>
                            {typeof v === "number"
                              ? key === "Año"
                                ? String(v)
                                : supportPercentage(key)
                                ? number(v * 100) + " %"
                                : kind === "electricity" && /^Tarifa\b/i.test(key)
                                ? sourceDecimal.format(v)
                                : key === "Variación (%)"
                                ? sourceDecimal.format(v) + " %"
                                : number(v)
                              : key === "Unidad" && typeof v === "string"
                                ? unitLabel(v)
                                : String(v)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                  <EvidenceLink
                    id={r.document_id}
                    locator={r.source_locator}
                    productName={kind !== "electricity" ? r.name : undefined}
                    providerName={kind === "electricity" ? r.name : undefined}
                    stratum={kind === "electricity" ? String(r.details.Estrato ?? r.details.stratum ?? "") : undefined}
                    marketName={typeof r.details.Ciudad === "string" ? r.details.Ciudad : undefined}
                    units={typeof r.details.Unidad === "string" ? r.details.Unidad : undefined}
                    month={r.observed_on}
                  >
                    Consultar fuente original
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
