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
import { MapButton } from "@/components/explore/ColombiaMap";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { photoFor } from "@/lib/images";
import { money, dateLabel } from "@/lib/market-types";
import type { InputDetail } from "@/lib/explore-types";
function Input({ id }: { id: string }) {
  const q = useSearchParams(),
    [department, setDepartment] = useState(q.get("department") || ""),
    [mode, setMode] = useState<InformationMode>("price");
  const { data, loading, error, retry } = useData<InputDetail>(
    "/api/explore/input?id=" +
      encodeURIComponent(id) +
      "&department=" +
      encodeURIComponent(department),
  );
  const photo = data
    ? photoFor(
        data.input.name,
        data.input.category + " " + data.input.presentation,
        "input",
      )
    : null;
  return (
    <>
      <Link className="back-link" href="/insumos">
        ← Insumos
      </Link>
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
                <MapButton kind="input" id={id} />
              </div>
            </div>
            <p className="photo-note">
              Fotografía ilustrativa del material. No representa el empaque ni
              certifica el producto comercial.
            </p>
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
                      input={id}
                      department={data.input.department}
                    >
                      Comprobar precio
                    </EvidenceLink>
                  </div>
                  <label className="form-field">
                    Departamento
                    <select
                      value={data.input.department}
                      onChange={(e) => setDepartment(e.target.value)}
                    >
                      {data.regions.map((r) => (
                        <option key={r.department}>{r.department}</option>
                      ))}
                    </select>
                  </label>
                </section>
                <PriceChart
                  points={data.history}
                  label={"Precio por " + data.input.presentation}
                />
                <section className="panel">
                  <h2>Compara la misma presentación</h2>
                  <div className="supply-list">
                    {data.regions.map((r) => (
                      <article key={r.department}>
                        <div>
                          <button
                            className="text-button"
                            onClick={() => setDepartment(r.department)}
                          >
                            {r.department}
                          </button>
                          <small>{dateLabel(r.observed_on, true)}</small>
                        </div>
                        <strong>{money(r.price)}</strong>
                        <EvidenceLink
                          id={r.document_id}
                          input={id}
                          department={r.department}
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
                  departamentos. La cobertura de precios no confirma
                  disponibilidad.
                </p>
                <div className="coverage-tags">
                  {data.regions.map((r) => (
                    <span key={r.department}>{r.department}</span>
                  ))}
                </div>
                <MapButton
                  kind="input"
                  id={id}
                  label="Ver cobertura en el mapa"
                />
                <EvidenceLink id={data.input.document_id} input={id}>
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
