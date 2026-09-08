"use client";
import { Suspense, use, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { PriceChart } from "@/components/marketplace/PriceChart";
import {
  DetailTabs,
  type InformationMode,
} from "@/components/explore/DetailTabs";
import { AppliedFilters } from "@/components/explore/AppliedFilters";
import { MapButton } from "@/components/explore/ColombiaMap";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { photoFor } from "@/lib/images";
import { money, dateLabel } from "@/lib/market-types";
import type { InputDetail } from "@/lib/explore-types";
function Input({ id }: { id: string }) {
  const q = useSearchParams(),
    [department, setDepartment] = useState(q.get("department") || ""),
    [municipality, setMunicipality] = useState(q.get("municipality") || ""),
    [mode, setMode] = useState<InformationMode>("price"),
    [scope, setScope] = useState(q.get("scope") || "department");
  const historical = false;
  const location = (r: { municipality: string; department: string }) =>
    r.municipality ? r.municipality + ", " + r.department : r.department;
  const { data, loading, error, retry } = useData<InputDetail>(
    "/api/explore/input?id=" +
      encodeURIComponent(id) +
      "&department=" +
      encodeURIComponent(department) +
      "&scope=" +
      scope +
      "&municipality=" +
      encodeURIComponent(municipality) +
      (historical ? "&history=all" : ""),
  );
  const photo = data
    ? photoFor(
        data.input.name,
        data.input.category + " " + data.input.presentation,
        "input",
      )
    : null;
  const filterControls = (
    <>
      <AppliedFilters
        items={[
          {
            label: "Cobertura",
            value:
              scope === "municipality" ? "Municipio" : "Promedio departamental",
          },
          {
            label: "Departamento",
            value: data?.input.department || department || "Colombia",
          },
          {
            label: "Municipio",
            value: data?.input.municipality || municipality,
          },
          { label: "Presentación", value: data?.input.presentation || "" },
          { label: "Marca", value: data?.input.brand || "" },
        ]}
      />
      <div className="catalog-controls">
        <label className="form-field">
          Cobertura del precio
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              setMunicipality("");
            }}
          >
            <option value="department">Promedio departamental</option>
            <option value="municipality">Precio por municipio</option>
          </select>
        </label>
      </div>
    </>
  );
  return (
    <>
      <Link
        className="back-link"
        href={
          "/insumos?" +
          new URLSearchParams({
            department,
            scope,
            history: historical ? "all" : "recent",
          })
        }
      >
        ← Insumos
      </Link>
      {(loading || error) && filterControls}
      {loading ? (
        <p role="status">Consultando insumo…</p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <div className="entity-hero">
              <img src={photo!.src} alt={photo!.alt} />
              <div>
                <span className="eyebrow">{data.input.category}</span>
                <h1>{data.input.name}</h1>
                <p>{data.input.presentation}</p>
                {data.input.brand && (
                  <p>
                    {data.input.brand} · Registro ICA:{" "}
                    {data.input.registration || "No indicado"}
                  </p>
                )}
                <div className="detail-actions">
                  <MapButton
                    kind="input"
                    id={id}
                    filters={{
                      scope,
                      region: data.input.department,
                      municipality: data.input.municipality,
                      history: historical ? "all" : "recent",
                    }}
                  />
                  <Link
                    className="button secondary"
                    href={
                      "/compare/inputs?" +
                      new URLSearchParams({
                        department,
                        municipality,
                        scope,
                        product: id,
                        history: historical ? "all" : "recent",
                      })
                    }
                  >
                    Comparar ubicaciones →
                  </Link>
                </div>
              </div>
            </div>
            <p className="photo-note">
              Fotografía ilustrativa del material. No representa el empaque ni
              certifica el producto comercial.
            </p>
            {filterControls}
            <DetailTabs mode={mode} onChange={setMode} />
            {mode === "price" ? (
              <>
                <section className="panel input-detail-summary">
                  <div>
                    <span>Precio de referencia</span>
                    <h2>{money(data.input.price)}</h2>
                    <p>
                      {data.input.presentation} ·{" "}
                      {dateLabel(data.input.observed_on)}
                    </p>
                    <EvidenceLink
                      id={data.input.document_id}
                      locator={data.input.source_locator}
                      input={id}
                      department={data.input.department}
                    >
                      Comprobar precio
                    </EvidenceLink>
                  </div>
                  <label className="form-field">
                    {scope === "municipality" ? "Municipio" : "Departamento"}
                    <select
                      value={JSON.stringify([
                        data.input.department,
                        data.input.municipality,
                      ])}
                      onChange={(e) => {
                        const [d, m] = JSON.parse(e.target.value);
                        setDepartment(d);
                        setMunicipality(m);
                      }}
                    >
                      {data.regions.map((r) => (
                        <option
                          key={location(r)}
                          value={JSON.stringify([r.department, r.municipality])}
                        >
                          {location(r)}
                        </option>
                      ))}
                    </select>
                  </label>
                </section>
                <PriceChart
                  key={[
                    id,
                    data.input.department,
                    data.input.municipality,
                    scope,
                    historical,
                  ].join(":")}
                  allowAll={historical}
                  points={data.history}
                  label={"Precio por " + data.input.presentation}
                  unit={"COP / " + data.input.presentation}
                />
                <section className="panel">
                  <h2>Compara la misma presentación</h2>
                  <div className="supply-list">
                    {[...data.regions]
                      .sort((a, b) => b.price - a.price)
                      .map((r) => (
                        <article key={location(r)}>
                          <div>
                            <button
                              className="text-button"
                              onClick={() => {
                                setDepartment(r.department);
                                setMunicipality(r.municipality);
                              }}
                            >
                              {location(r)}
                            </button>
                            <small>{dateLabel(r.observed_on, true)}</small>
                          </div>
                          <strong>{money(r.price)}</strong>
                          <EvidenceLink
                            id={r.document_id}
                            locator={r.source_locator}
                            input={id}
                            department={location(r)}
                          >
                            Ver fuente
                          </EvidenceLink>
                        </article>
                      ))}
                  </div>
                </section>
                <Link className="button primary" href="/plan?tab=budget">
                  Usar como referencia para mi presupuesto →
                </Link>
              </>
            ) : (
              <section className="panel supply-empty">
                <h2>No hay datos de existencias de este insumo</h2>
                <p>
                  DANE publica precios de referencia, pero esta fuente no
                  informa cuántas unidades tienen los proveedores ni cuáles
                  están disponibles para comprar.
                </p>
                <h3>¿Dónde hay referencias?</h3>
                <p>
                  Este insumo tiene precios publicados en {data.regions.length}{" "}
                  ubicaciones. La cobertura de precios no confirma
                  disponibilidad.
                </p>
                <div className="coverage-tags">
                  {data.regions.map((r) => (
                    <span key={location(r)}>{location(r)}</span>
                  ))}
                </div>
                <MapButton
                  kind="input"
                  id={id}
                  label="Ver cobertura en el mapa"
                  filters={{
                    scope,
                    region: data.input.department,
                    municipality: data.input.municipality,
                    history: historical ? "all" : "recent",
                  }}
                />
                <EvidenceLink
                  id={data.input.document_id}
                  locator={data.input.source_locator}
                  input={id}
                >
                  Consultar la fuente
                </EvidenceLink>
              </section>
            )}
            <p className="notice">
              La presencia de un insumo en la fuente no recomienda su uso ni
              establece una dosis.
            </p>
          </>
        )
      )}
    </>
  );
}
export default function InputPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Suspense fallback={<p>Cargando insumo…</p>}>
      <Input id={id} />
    </Suspense>
  );
}
