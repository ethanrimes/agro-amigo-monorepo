"use client";

import { EvidenceLink } from "./EvidenceLink";
import { IoDownloadOutline, IoShieldCheckmarkOutline } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { PdfViewer } from "@/components/planning/PdfViewer";
import { WorkbookViewer } from "@/components/planning/WorkbookViewer";
import { SupplyEvidenceRecords } from "./SupplyEvidenceRecords";
import type { Evidence, VariationDisagreementSource } from "@/lib/planning-types";
import { evidencePeriod } from "@/lib/evidence-period";
import { evidenceValue, evidenceUnitNote } from "@/lib/evidence-value";
import { dateLabel, number } from "@/lib/market-types";
import { workbookLocation } from "@/lib/workbook-locator";
import { evidencePage } from "@/lib/pdf-locator";
import { evidenceQueryContext } from "@/lib/evidence-query-context";
const labels: Record<string, string> = {
  product_name: "Producto",
  rangos: "Lluvia habitual (intervalo)",
  rango: "Temperatura habitual (°C)",
  TEXTURA: "Textura",
  PROFUNDIDA: "Profundidad",
  FERTILIDAD: "Fertilidad",
  ACIDEZ: "Acidez",
  DRENAJE: "Drenaje",
  PAISAJE: "Paisaje",
  TIPO_RELIE: "Relieve",
  PENDIENT_1: "Código de pendiente (IGAC)",
  CLIMA_1: "Clima ambiental",
  UCSuelo: "Unidad de suelo",
  tipo: "Tipo de erosión",
  clas: "Forma de erosión",
  gra: "Grado de erosión",
  unit: "Unidad",
  period: "Frecuencia",
  food_name: "Alimento",
  market_name: "Mercado",
  market: "Mercado",
  quantity_kg: "Cantidad (kg)",
  reporting_days: "Días con reporte",
  period_start: "Inicio del período",
  first_reported_on: "Primer reporte",
  crop: "Cultivo",
  variety: "Variedad / sistema",
  reference_year: "Año de referencia",
  physical_state: "Estado del producto",
  planted_ha: "Área sembrada (ha)",
  harvested_ha: "Área cosechada (ha)",
  production_t: "Producción (t)",
  yield_kg_ha: "Rendimiento (kg/ha)",
  source_rows: "Registros en el archivo",
  source_row: "Registro original",
  crop_key: "Capa",
  classification: "Categoría de aptitud",
  area_ha: "Área mapeada (ha)",
  samples: "Muestras de laboratorio",
  ph_samples: "Muestras con pH",
  ph_median: "pH mediano",
  ph_low: "pH percentil 25",
  ph_high: "pH percentil 75",
  organic_matter_median: "Materia orgánica mediana (%)",
  oldest: "Análisis más antiguo",
  newest: "Análisis más reciente",
  activity: "Actividad",
  percentages: "Porcentajes de enero a diciembre",
  name: "Insumo",
  department: "Departamento",
  observed_on: "Fecha",
  presentation: "Presentación",
  price: "Precio en la moneda de la fuente",
  currency: "Moneda",
  basis: "Tipo de precio",
  min_price: "Mínimo",
  max_price: "Máximo",
  source_locator: "Ubicación del dato",
};

function isVariationDisagreementSource(value: unknown): value is VariationDisagreementSource {
  if (!value || typeof value !== "object") return false;
  const source = value as Partial<VariationDisagreementSource>;
  return typeof source.label === "string" && source.label.length > 0 &&
    typeof source.document_id === "string" && /^[a-f0-9]{64}$/i.test(source.document_id) &&
    Number.isInteger(source.page) && Number(source.page) > 0 &&
    typeof source.locator === "string" && source.locator.length > 0;
}

export function EvidenceContent({
  id,
  query = "",
}: {
  id: string;
  query?: string;
}) {
  const q = new URLSearchParams(query);
  const { data, loading, error, retry } = useData<Evidence>(
    "/api/evidence/" + encodeURIComponent(id) + "?" + q.toString(),
  );
  const initial = evidencePage(q.get("page"), q.get("locator"));
  const workbookTarget = workbookLocation(q.get("locator"));
  const initialSheet = q.get("sheet") || workbookTarget?.sheet || "";
  const initialRow = Math.max(1, Number(q.get("row")) || workbookTarget?.row || 1);
  const initialColumn = Math.max(0, Number(q.get("col")) || workbookTarget?.column || 0);
  const queryContext = evidenceQueryContext(data?.metadata.query_context, q, data?.records);
  const variationSources = Array.isArray(data?.metadata.variation_disagreement_sources)
    ? data.metadata.variation_disagreement_sources.filter(isVariationDisagreementSource)
    : [];
  const supplySheet = typeof data?.metadata.supply_summary_sheet === "string" ? data.metadata.supply_summary_sheet : "";
  const supplyIsAnotherSheet = Boolean(initialSheet && supplySheet && initialSheet !== supplySheet);
  const unitNote = evidenceUnitNote(data?.records);
  return (
    <>
      {loading ? (
        <div className="empty-state" role="status">
          Abriendo documento…
        </div>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <section className="evidence-heading panel">
              <span className="source-badge">
                {data.kind === "extract"
                  ? "Extracto verificable"
                  : data.kind === "methodology"
                    ? "Método de cálculo"
                    : "Documento de la fuente"}
              </span>
              <h2>{data.title}</h2>
              <p>
                {data.publisher} · Referencia: {evidencePeriod(data)}
              </p>
              {queryContext.length > 0 && (
                <div className="applied-filters" aria-label="Filtros de los datos consultados">
                  <span>Consulta actual</span>
                  {queryContext.map((filter, index) => (
                      <span className="filter-chip" key={index}>{filter.label}: {filter.value}</span>
                    ),
                  )}
                </div>
              )}
              {unitNote && <p className="inline-note" data-testid="source-unit-conversion">{unitNote}</p>}
              {typeof data.metadata.supply_summary_note === "string" && (
                supplyIsAnotherSheet ? (
                  <details className="evidence-notes" data-testid="other-sheet-supply-summary">
                    <summary>Este archivo también contiene abastecimiento (hoja {supplySheet})</summary>
                    <p className="inline-note" data-testid="supply-summary-note">
                      {data.metadata.supply_summary_note}{" "}
                      <a href={"/evidence/" + encodeURIComponent(data.id) + "?sheet=" + encodeURIComponent(supplySheet) + "&row=11"}>
                        Ver celdas originales de abastecimiento ↗
                      </a>
                    </p>
                  </details>
                ) : (
                  <p className="inline-note" data-testid="supply-summary-note">
                    {data.metadata.supply_summary_note}{" "}
                    {supplySheet && (
                      <a href={"/evidence/" + encodeURIComponent(data.id) + "?sheet=" + encodeURIComponent(supplySheet) + "&row=11"}>
                        Ver celdas originales de abastecimiento ↗
                      </a>
                    )}
                    {typeof data.metadata.supply_summary_page === "number" && (
                      <a href={"/evidence/" + encodeURIComponent(data.id) + "?page=" + data.metadata.supply_summary_page}>
                        Ver tabla original de abastecimiento ↗
                      </a>
                    )}
                  </p>
                )
              )}
              {typeof data.metadata.source_location_code_note === "string" && (
                <p className="inline-note" data-testid="source-location-code-conflict">
                  {data.metadata.source_location_code_note}
                </p>
              )}
              {typeof data.metadata.review_note === "string" && (
                <p className="inline-note">{data.metadata.review_note}</p>
              )}
              {typeof data.metadata.city_pdf_publication_note === "string" && (
                <p className="inline-note" role="status">{data.metadata.city_pdf_publication_note}</p>
              )}
              {typeof data.metadata.city_partial_review_note === "string" && (
                <p className="inline-note" role="status">{data.metadata.city_partial_review_note}</p>
              )}
              {typeof data.metadata.record_review_note === "string" && (
                <p className="inline-note">{data.metadata.record_review_note}</p>
              )}
              {typeof data.metadata.identity_review_note === "string" && (
                <p className="inline-note">{data.metadata.identity_review_note}</p>
              )}
              {typeof data.metadata.price_disagreement_note === "string" && (
                <p className="inline-note">{data.metadata.price_disagreement_note}</p>
              )}
              {typeof data.metadata.presentation_source_note === "string" && (
                <p className="inline-note">{data.metadata.presentation_source_note}</p>
              )}
              {typeof data.metadata.variation_disagreement_note === "string" && (
                <div className="inline-note" data-testid="variation-disagreement-note">
                  <p>{data.metadata.variation_disagreement_note}</p>
                  {variationSources.map((source, index) => (
                    <p key={`${source.document_id}:${index}`}>
                      <a href={`/evidence/${encodeURIComponent(source.document_id)}?page=${source.page}`}>
                        {source.label} · {source.locator} ↗
                      </a>
                    </p>
                  ))}
                </div>
              )}
              {typeof data.metadata.date_resolution_note === "string" && (
                <p className="inline-note">
                  {data.metadata.date_resolution_note}{" "}
                  {typeof data.metadata.date_evidence_url === "string" && (
                    <a href={data.metadata.date_evidence_url} target="_blank" rel="noreferrer">
                      Consultar publicación que confirma la fecha ↗
                    </a>
                  )}
                </p>
              )}
              <div className="evidence-actions">
                <a
                  className="button primary"
                  href={"/api/evidence/" + data.id + "/content"}
                  download
                >
                  <IoDownloadOutline /> Descargar archivo
                </a>
                <a
                  className="button secondary"
                  href={data.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Sitio de la entidad ↗
                </a>
              </div>
              <details className="evidence-notes">
                <summary>Acerca de esta fuente y sus datos</summary>
                {data.kind === "extract" && (
                  <p className="inline-note">
                    Este extracto fue preparado por AgroAmigo a partir de los
                    datos oficiales. Abajo puedes consultar los archivos
                    originales conservados.
                  </p>
                )}
                {typeof data.metadata.note === "string" && (
                  <p className="inline-note">{data.metadata.note}</p>
                )}
                {typeof data.metadata.method === "string" && (
                  <p className="inline-note">{data.metadata.method}</p>
                )}
              </details>
            </section>
            <SupplyEvidenceRecords id={data.id} records={data.records} query={q} />
            {data.media_type === "application/pdf" ? (
              <>
                <PdfViewer id={data.id} initialPage={initial} />
                {data.records?.some((record) => record.kind === "supply-daily-summary") ? (
                  <section className="panel evidence-records" data-testid="daily-pdf-supply-records">
                    <details>
                      <summary>Abastecimiento diario: {data.records.length} celdas del Cuadro 1</summary>
                      <p>Toneladas impresas; la marca “p” identifica datos provisionales. Los espacios en blanco indican datos no reportados; el total se muestra por separado y no se suma a los mercados.</p>
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>Fecha</th><th>Mercado</th><th>Toneladas</th><th>Marca</th><th>Original</th></tr></thead>
                          <tbody>
                            {data.records.map((record, index) => {
                              const details = record.details as Record<string, unknown> | undefined;
                              const page = Number(details?.source_page);
                              const quantity = details?.quantity_tonnes;
                              const query = new URLSearchParams({ page: String(page), locator: String(record.source_locator) });
                              return (
                                <tr key={index}>
                                  <td>{String(record.observed_on).slice(0, 10)}</td>
                                  <td>{String(record.name)}</td>
                                  <td>{typeof quantity === "number" ? quantity.toLocaleString("es-CO") : "Sin reporte"}</td>
                                  <td>{details?.provisional_mark === "p" ? "Provisional (p)" : "Sin marca p"}</td>
                                  <td><a href={`/evidence/${encodeURIComponent(data.id)}?${query.toString()}`}>Página {page}, columna {String(details?.column)}</a></td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  </section>
                ) : null}
              </>
            ) : data.media_type.includes("spreadsheet") ||
              data.media_type === "application/vnd.ms-excel" ? (
              <WorkbookViewer
                key={`${data.id}:${initialSheet}:${initialRow}:${initialColumn}`}
                id={data.id}
                initialSheet={initialSheet}
                initialRow={initialRow}
                initialColumn={initialColumn}
              />
            ) : data.media_type.startsWith("image/") ? (
              <section className="panel source-image">
                <img
                  src={"/api/evidence/" + data.id + "/content"}
                  alt={data.title}
                />
              </section>
            ) : data.text ? (
              <section className="panel">
                <h2>Texto de la publicación</h2>
                <pre className="evidence-text">{data.text}</pre>
              </section>
            ) : data.records?.length ? (
              <section className="panel evidence-records">
                <h2>Datos de esta consulta</h2>
                <p>Se conservan las unidades y la referencia del archivo.</p>
                {data.records.length > 100 && (
                  <p className="field-help">
                    Se muestran 100 de {number(data.records.length)} registros consultados.
                    Descarga el original para consultar el archivo completo.
                  </p>
                )}
                {data.records.slice(0, 100).map((r, i) => (
                  <details key={i} open={data.records!.length <= 3}>
                    <summary>
                      {String(
                        r.variety ||
                          r.crop ||
                          r.classification ||
                          r.product_name ||
                          r.food_name ||
                          r.name ||
                          r.fecha ||
                          "Registro " + (i + 1),
                      )}
                    </summary>
                    <dl>
                      {Object.entries(r).map(([k, v]) => (
                        <div key={k}>
                          <dt>{labels[k] || k.replaceAll("_", " ")}</dt>
                          <dd>
                            {evidenceValue(k, v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                ))}
              </section>
            ) : (
              <section className="panel">
                <h2>Archivo de datos de la entidad</h2>
                <p>
                  El original está disponible para descargar. Los enlaces desde
                  el cultivo o insumo abren los registros correspondientes a tu
                  consulta.
                </p>
              </section>
            )}
            {data.parents.length > 0 && (
              <section className="panel evidence-parents">
                <h2>Archivos originales conservados</h2>
                {data.parents.map((p) => (
                  <EvidenceLink key={p.id} id={p.id}>
                    {p.title} →
                  </EvidenceLink>
                ))}
              </section>
            )}
            <details className="source-explanation">
              <summary>
                <IoShieldCheckmarkOutline /> Fecha de consulta y trazabilidad
              </summary>
              <dl className="evidence-audit">
                <dt>Conservado en Azure</dt>
                <dd>
                  {new Date(data.retrieved_at).toLocaleString("es-CO", {
                    timeZone: "America/Bogota",
                  })}{" "}
                  (Colombia)
                </dd>
                <dt>Tamaño</dt>
                <dd>{number(data.bytes / 1024)} KB</dd>
                <dt>
                  {data.id.startsWith("weather-")
                    ? "Identificador de la consulta"
                    : "Identificador de integridad SHA-256"}
                </dt>
                <dd className="source-hash">
                  {data.id.replace(/^(weather|spatial)-/, "")}
                </dd>
              </dl>
              {typeof data.metadata.description === "string" && (
                <p>{data.metadata.description}</p>
              )}
              <p>
                Una actualización de la fuente crea una nueva versión; el
                documento de esta consulta conserva su identificador.
              </p>
            </details>
          </>
        )
      )}
    </>
  );
}
