"use client";
import { Suspense, use, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
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
import type { InputAliasChoice, InputDetail } from "@/lib/explore-types";
import { inputLocationDisplayLabel, inputMunicipalityDisplayLabel } from "@/lib/input-locations";
import { wageBasisNote, wageChartLabel, wagePresentationDisplay, wageRateUnitDisplay } from "@/lib/wage-basis-display";
import { inputPresentationSourceNote } from "@/lib/input-source-notes";
function Input({ id }: { id: string }) {
  const router = useRouter();
  const q = useSearchParams(),
    [department, setDepartment] = useState(q.get("department") || ""),
    [municipality, setMunicipality] = useState(q.get("municipality") || ""),
    [mode, setMode] = useState<InformationMode>("price"),
    [scope, setScope] = useState(q.get("scope") || "department");
  const [historical, setHistorical] = useState(q.get("history") === "all");
  const location = (r: { municipality: string; department: string }) =>
    inputLocationDisplayLabel(r.department, r.municipality);
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
  const { data: aliasOptions, loading: aliasesLoading } = useData<InputAliasChoice[]>(
    "/api/explore/input-aliases?" +
      new URLSearchParams({ id, department, municipality, scope }).toString(),
  );
  // A browser may retain the previous release's cacheable detail response.
  const currentQuotes = data?.current_quotes ?? (data ? [data.input] : []);
  const sourceNotes = [...new Set(currentQuotes.map(inputPresentationSourceNote).filter(Boolean))];
  useEffect(() => {
    if (data?.input.id && data.input.id !== id) {
      router.replace(`/insumo/${encodeURIComponent(data.input.id)}${window.location.search}${window.location.hash}`);
    }
  }, [data?.input.id, id, router]);
  const aliasChooser = (
    <SearchableSelect
      label="Línea comercial del insumo"
      value=""
      allowClear={false}
      emptyLabel="Elige una línea para consultar su precio e historial"
      placeholder="Busca nombre, marca, presentación o lugar"
      options={(aliasOptions || []).map((option) => ({
        id: option.id,
        label: [option.name, option.product_line, option.presentation].filter(Boolean).join(" · "),
        detail: [option.brand, inputLocationDisplayLabel(option.department, option.municipality), dateLabel(option.observed_on), money(option.price)].filter(Boolean).join(" · "),
      }))}
      onChange={(chosen) => {
        const option = aliasOptions?.find((item) => item.id === chosen);
        if (!option) return;
        router.push("/insumo/" + encodeURIComponent(option.id) + "?" + new URLSearchParams({
          department: option.department,
          municipality: option.municipality,
          scope,
          history: historical ? "all" : "recent",
        }).toString());
      }}
    />
  );
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries({
      department: data?.input.department || department,
      municipality: data?.input.municipality || municipality,
      scope,
      history: historical ? "all" : "recent",
    })) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    const search = params.toString();
    const next = window.location.pathname + (search ? "?" + search : "") + window.location.hash;
    if (next !== window.location.pathname + window.location.search + window.location.hash)
      window.history.replaceState(null, "", next);
  }, [data?.input.department, data?.input.municipality, department, municipality, scope, historical]);
  const photo = data
    ? photoFor(
        data.input.name,
        data.input.category + " " + data.input.presentation,
        "input",
      )
    : null;
  const locationId = (r: { department: string; municipality: string }) =>
    JSON.stringify([r.department, r.municipality]);
  const chooseLocation = (chosen: string) => {
    const [d, m] = JSON.parse(chosen) as [string, string];
    setDepartment(d);
    setMunicipality(m);
  };
  const locationChooser = (label: string) => data && (
    <SearchableSelect
      label={label}
      placeholder="Busca un municipio o departamento…"
      value={locationId(data.input)}
      selectedLabel={location(data.input)}
      options={data.regions.map((r) => ({
        id: locationId(r),
        label: location(r),
        detail: [r.identity_conflict ? "Hay precios distintos" : money(r.price), wagePresentationDisplay(r.name, r.presentation), dateLabel(r.observed_on)].join(" · "),
      }))}
      onChange={chooseLocation}
      allowClear={false}
    />
  );
  const rankedLocations = [...(data?.regions || [])].sort((a, b) => b.price - a.price);
  const comparisonLocations = rankedLocations.slice(0, 6);
  const chosenLocation = data && rankedLocations.find((r) => locationId(r) === locationId(data.input));
  if (chosenLocation && !comparisonLocations.some((r) => locationId(r) === locationId(chosenLocation)))
    comparisonLocations.push(chosenLocation);
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
            value: inputMunicipalityDisplayLabel(data?.input.municipality || municipality),
          },
          { label: "Historial", value: historical ? "Todo el historial" : "Últimos 12 meses" },
          { label: "Presentación", value: data ? wagePresentationDisplay(data.input.name, data.input.presentation) : "" },
          { label: "Marca", value: data?.input.brand || "" },
          { label: "Línea", value: data?.input.product_line || "" },
        ]}
      />
      <div className="catalog-controls">
        <label className="form-field">
          Historial de precios
          <select
            aria-label="Historial de precios"
            value={historical ? "all" : "recent"}
            onChange={(event) => setHistorical(event.target.value === "all")}
          >
            <option value="recent">Últimos 12 meses</option>
            <option value="all">Todo el historial</option>
          </select>
        </label>
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
      {(loading || aliasesLoading || error || (!data && Boolean(aliasOptions?.length))) && filterControls}
      {loading || aliasesLoading ? (
        <p role="status">Consultando insumo…</p>
      ) : !data && aliasOptions?.length ? (
        <section className="panel">
          <h1>{aliasOptions.length === 1 ? "Consultar la referencia disponible" : "Elige la línea del insumo"}</h1>
          <p>
            {aliasOptions.length === 1
              ? "Esta referencia anterior tiene una línea disponible con los filtros elegidos. Abre su historial y su fuente."
              : "Esta referencia anterior reúne líneas comerciales distintas. Cada línea tiene su propio historial y fuente; elige la que quieres consultar."}
          </p>
          {aliasChooser}
        </section>
      ) : !data && error === "No encontramos esta referencia." ? (
        <section className="panel" role="status">
          <h1>Sin precio para esta cobertura</h1>
          <p>
            Esta referencia no tiene un precio {scope === "municipality" ? "municipal" : "departamental"}
            {" "}publicado con los filtros elegidos. Puedes cambiar la cobertura o
            consultar el catálogo de insumos de la zona.
          </p>
          <button className="btn-secondary" onClick={() => {
            setScope(scope === "municipality" ? "department" : "municipality");
            setMunicipality("");
          }}>
            {scope === "municipality" ? "Consultar promedio departamental" : "Consultar precios municipales"}
          </button>
          <p><Link href={"/insumos?" + new URLSearchParams({
            department, municipality, scope, history: historical ? "all" : "recent",
          }).toString()}>Ver insumos de esta zona →</Link></p>
        </section>
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
                <p>{wagePresentationDisplay(data.input.name, data.input.presentation)}</p>
                {data.input.product_line && <p>Línea: {data.input.product_line}</p>}
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
              {photo!.alt} No certifica el producto comercial.
            </p>
            {aliasOptions?.length ? (
              <section className="panel">
                <h2>Otras líneas comerciales de esta referencia</h2>
                <p>El historial anterior se conserva. Las líneas separadas tienen precios y fuentes propios.</p>
                {aliasChooser}
              </section>
            ) : null}
            {filterControls}
            {sourceNotes.map((note) => <p className="inline-note" key={note}>{note}</p>)}
            <DetailTabs mode={mode} onChange={setMode} />
            {mode === "price" ? (
              <>
                <section className="panel input-detail-summary">
                  <div>
                    <span>Precio de referencia</span>
                    {new Set(currentQuotes.map((quote) => quote.price)).size > 1 ? (
                      <div role="alert">
                        <h2>Hay precios distintos publicados para esta fecha y ubicación</h2>
                        <ul>
                          {currentQuotes.map((quote) => (
                            <li key={`${quote.source_input_id || quote.id}:${quote.document_id}:${quote.source_locator}`}>
                              <strong>{money(quote.price)}</strong> · {dateLabel(quote.observed_on)} · {quote.source_name || quote.name}
                              <br />
                              <EvidenceLink
                                id={quote.document_id}
                                locator={quote.source_locator}
                                input={quote.source_input_id || id}
                                department={quote.department}
                                municipality={quote.municipality}
                                productName={quote.source_name || quote.name}
                                presentation={quote.presentation}
                                month={quote.observed_on}
                              >
                                Comprobar fuente original
                              </EvidenceLink>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <>
                        <h2>{money(currentQuotes[0]?.price ?? data.input.price)}</h2>
                        <p>
                          {wagePresentationDisplay(data.input.name, data.input.presentation)} ·{" "}
                          {dateLabel(data.input.observed_on)}
                        </p>
                        {(currentQuotes.length ? currentQuotes : [data.input]).map((quote) => (
                          <EvidenceLink
                            key={`${quote.source_input_id || quote.id}:${quote.document_id}:${quote.source_locator}`}
                            id={quote.document_id}
                            locator={quote.source_locator}
                            input={quote.source_input_id || id}
                            department={quote.department}
                            municipality={quote.municipality}
                            productName={quote.source_name || quote.name}
                            presentation={quote.presentation}
                            month={quote.observed_on}
                          >
                            {currentQuotes.length > 1 ? `Comprobar fuente · ${quote.source_name || quote.name}` : "Comprobar precio"}
                          </EvidenceLink>
                        ))}
                      </>
                    )}
                    {wageBasisNote(data.input.name, data.input.presentation) && (
                      <small>{wageBasisNote(data.input.name, data.input.presentation)}</small>
                    )}
                  </div>
                  <SearchableSelect
                    label={scope === "municipality" ? "Municipio" : "Departamento"}
                    placeholder={scope === "municipality" ? "Busca un municipio…" : "Busca un departamento…"}
                    value={JSON.stringify([data.input.department, data.input.municipality])}
                    selectedLabel={location(data.input)}
                    options={data.regions.map((r) => ({
                      id: JSON.stringify([r.department, r.municipality]),
                      label: location(r),
                    }))}
                    onChange={(id) => {
                      const [d, m] = JSON.parse(id) as [string, string];
                      setDepartment(d);
                      setMunicipality(m);
                    }}
                    allowClear={false}
                  />
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
                  label={wageChartLabel(data.input.name, data.input.presentation)}
                  unit={wageRateUnitDisplay(data.input.name, data.input.presentation)}
                  evidenceContext={{
                    input: id,
                    productName: data.input.name,
                    department: data.input.department,
                    municipality: data.input.municipality,
                    presentation: data.input.presentation,
                  }}
                />
                <section className="panel">
                  <h2>Compara la misma presentación</h2>
                  <div className="applied-filters" aria-label="Alcance de la comparación">
                    <span>Comparación nacional</span>
                    <span className="filter-chip">Colombia</span>
                    <span className="filter-chip">{historical ? "Todo el historial" : "Últimos 12 meses"}</span>
                    <span className="filter-chip">{wagePresentationDisplay(data.input.name, data.input.presentation)}</span>
                  </div>
                  <p>
                    La ubicación elegida ({location(data.input)}) determina el precio y el historial de arriba.
                    Aquí se comparan ubicaciones de toda Colombia con la misma presentación;
                    cada una muestra la fecha y la fuente de su propio último reporte dentro del período.
                  </p>
                  {data.regions.length > 6 && (
                    <>
                      <p>Se muestran las seis ubicaciones con mayor precio y la ubicación elegida. Busca entre las {data.regions.length} ubicaciones para consultar otra.</p>
                      {locationChooser("Comparar ubicación de este insumo")}
                    </>
                  )}
                  <div className="supply-list">
                    {comparisonLocations.map((r) => (
                        <article key={locationId(r)} data-location-id={locationId(r)}>
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
                            <small className="filter-chip">Reporte: {dateLabel(r.observed_on)}</small>
                          </div>
                          {r.identity_conflict ? (
                            <div role="alert">
                              <strong>Precios distintos para esta fecha</strong>
                              <ul>
                                {(r.identity_conflict_quotes || []).map((quote) => (
                                  <li key={`${quote.source_input_id}:${quote.document_id}:${quote.source_locator}`}>
                                    {money(Number(quote.price))} · {quote.source_name}
                                    {quote.document_id && <EvidenceLink
                                      id={quote.document_id}
                                      locator={quote.source_locator}
                                      input={quote.source_input_id || id}
                                      department={r.department}
                                      municipality={r.municipality}
                                      productName={quote.source_name || r.name}
                                      presentation={r.presentation}
                                      month={String(quote.observed_on)}
                                    >Consultar fuente</EvidenceLink>}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : (
                            <>
                              <strong>{money(r.price)}</strong>
                              <EvidenceLink
                                id={r.document_id}
                                locator={r.source_locator}
                                input={r.source_input_id || id}
                                department={r.department}
                                municipality={r.municipality}
                                productName={r.source_name || data.input.name}
                                presentation={data.input.presentation}
                                month={r.observed_on}
                              >
                                Ver fuente
                              </EvidenceLink>
                            </>
                          )}
                        </article>
                      ))}
                  </div>
                </section>

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
                  {data.regions.length <= 6
                    ? data.regions.map((r) => <span key={locationId(r)}>{location(r)}</span>)
                    : <span>{location(data.input)}</span>}
                </div>
                {data.regions.length > 6 && locationChooser("Consultar ubicación con referencias")}
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
                  department={data.input.department}
                  municipality={data.input.municipality}
                  productName={data.input.name}
                  presentation={data.input.presentation}
                  month={data.input.observed_on}
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
