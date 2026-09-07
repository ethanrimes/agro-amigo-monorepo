"use client";

import { EvidenceLink } from "./EvidenceLink";
import { IoDownloadOutline, IoShieldCheckmarkOutline } from "react-icons/io5";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { PdfViewer } from "@/components/planning/PdfViewer";
import type { Evidence } from "@/lib/planning-types";
import { dateLabel, number } from "@/lib/market-types";
const labels: Record<string, string> = {
  product_name: "Producto",
  unit: "Unidad",
  period: "Frecuencia",
  food_name: "Alimento",
  market_name: "Mercado",
  quantity_kg: "Cantidad (kg)",
  reporting_days: "Días con reporte",
  period_start: "Mes",
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
  price: "Precio (COP)",
  source_locator: "Ubicación del dato",
};
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
  const initial = Math.max(1, Number(q.get("page")) || 1);
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
                {data.publisher} · Referencia: {data.reference_period}
              </p>
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
            {data.media_type === "application/pdf" ? (
              <PdfViewer id={data.id} initialPage={initial} />
            ) : data.text ? (
              <section className="panel">
                <h2>Texto de la publicación</h2>
                <pre className="evidence-text">{data.text}</pre>
              </section>
            ) : data.records?.length ? (
              <section className="panel evidence-records">
                <h2>Datos de esta consulta</h2>
                <p>Se conservan las unidades y la referencia del archivo.</p>
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
                            {v === null
                              ? "Sin dato"
                              : Array.isArray(v)
                                ? v.join(" · ")
                                : typeof v === "number"
                                  ? number(v)
                                  : typeof v === "object"
                                    ? JSON.stringify(v)
                                    : String(v)}
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
                  {data.id.replace("weather-", "")}
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
