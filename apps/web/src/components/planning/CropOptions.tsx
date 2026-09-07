"use client";
import { useState } from "react";
import { SearchBox } from "@/components/ui/SearchBox";
import { photoFor } from "@/lib/images";
import {
  IoLeafOutline,
  IoArrowForward,
  IoLocationOutline,
} from "react-icons/io5";
import type { CropReference, FarmData } from "@/lib/planning-types";
import { cropMapKeys, fold, MONTHS } from "@/lib/planning-math";
import { number, dateLabel } from "@/lib/market-types";
import { EvidenceLink } from "./EvidenceLink";
export function CropOptions({
  data,
  select,
}: {
  data: FarmData;
  select: (crop: CropReference) => void;
}) {
  const [query, setQuery] = useState(""),
    [month, setMonth] = useState(new Date().getMonth() + 1),
    [more, setMore] = useState(false);
  const candidates = data.crops
    .filter(
      (c) => !query || fold(c.crop + " " + c.variety).includes(fold(query)),
    )
    .map((c) => {
      const keys = cropMapKeys(c.crop, c.variety, month);
      const mapped = data.suitability.filter((s) => keys.includes(s.crop_key)),
        total = mapped.reduce((a, s) => a + s.area_ha, 0),
        suitable = mapped
          .filter((s) =>
            ["aptitud alta", "aptitud media"].includes(fold(s.classification)),
          )
          .reduce((a, s) => a + s.area_ha, 0);
      return { c, mapped, total, suitable };
    })
    .sort(
      (a, b) => b.suitable - a.suitable || b.c.harvested_ha - a.c.harvested_ha,
    );
  const soil = data.soil;
  return (
    <>
      <section className="plan-intro panel">
        <span className="eyebrow">
          <IoLocationOutline /> {data.municipality.name},{" "}
          {data.municipality.department}
        </span>
        <h2>Un punto de partida para elegir</h2>
        <p>
          Cultivos reportados en tu municipio, junto con su aptitud regional
          cuando hay un mapa disponible. Explora una opción y después haz sus
          cuentas.
        </p>
        <div className="form-grid">
          <div className="form-field">
            <span>Buscar cultivo</span>
            <SearchBox
              label="Buscar cultivo"
              placeholder="Café, aguacate, frijol…"
              value={query}
              onChange={(v) => {
                setQuery(v);
                setMore(false);
              }}
              options={data.crops.map((c) => ({
                id: c.crop_code,
                label: c.variety,
                detail: c.crop,
              }))}
            />
          </div>
          <label className="form-field">
            Mes que estás considerando
            <select value={month} onChange={(e) => setMonth(+e.target.value)}>
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
            <small>
              Determina el semestre de los mapas de papa, maíz y cebolla.
            </small>
          </label>
        </div>
      </section>
      <div className="crop-options">
        {candidates
          .slice(0, more ? undefined : 9)
          .map(({ c, mapped, total, suitable }) => (
            <article className="crop-option panel" key={c.crop_code}>
              <div className="crop-option-photo">
                <img
                  src={photoFor(c.crop).src}
                  alt={photoFor(c.crop).alt}
                  loading="lazy"
                />
                <span>
                  <IoLocationOutline /> {data.municipality.name}
                </span>
              </div>
              <div className="crop-option-title">
                <span className="crop-option-icon">
                  <IoLeafOutline />
                </span>
                <div>
                  <h3>{c.variety}</h3>
                  <span>
                    {c.cycle === "Permanente"
                      ? "Cultivo permanente"
                      : "Cultivo transitorio"}
                  </span>
                </div>
              </div>
              {mapped.length > 0 ? (
                <>
                  <div className="aptitude-result">
                    <strong>{number(suitable)}</strong>
                    <span>
                      hectáreas con aptitud alta o media en el municipio
                    </span>
                  </div>
                  <div
                    className="aptitude-bar"
                    role="img"
                    aria-label={`${number(total ? (suitable / total) * 100 : 0)} por ciento del área evaluada con aptitud alta o media`}
                  >
                    <span
                      style={{
                        width: (total ? (suitable / total) * 100 : 0) + "%",
                      }}
                    />
                  </div>
                  <small>
                    {number(total ? (suitable / total) * 100 : 0)} % del área
                    evaluada por esta capa.
                  </small>
                  <details>
                    <summary>Ver categorías y alcance del mapa</summary>
                    <p>{mapped[0].title}. Referencia a escala 1:100.000.</p>
                    {mapped.map((s) => (
                      <p key={s.classification}>
                        {s.classification}: {number(s.area_ha)} ha
                      </p>
                    ))}
                    <EvidenceLink
                      id={mapped[0].document_id}
                      municipality={data.municipality.id}
                    >
                      Consultar mapa y datos de UPRA
                    </EvidenceLink>
                  </details>
                </>
              ) : (
                <p className="coverage-note">
                  Sin mapa de aptitud integrado para esta variedad o sistema. La
                  producción local aporta contexto.
                </p>
              )}
              <dl className="crop-local-data">
                <div>
                  <dt>Rendimiento local de referencia</dt>
                  <dd>
                    {c.yield_kg_ha
                      ? number(c.yield_kg_ha) + " kg/ha"
                      : "Sin dato"}
                  </dd>
                </div>
                <div>
                  <dt>Área cosechada reportada</dt>
                  <dd>{number(c.harvested_ha)} ha</dd>
                </div>
              </dl>
              <p className="privacy-note">
                EVA {c.reference_year} · {c.physical_state} ·{" "}
                {c.cycle === "Permanente"
                  ? "Producción anual en áreas cosechadas."
                  : "Producción por área cosechada; puede reunir ambos semestres."}
              </p>
              <EvidenceLink
                id={c.document_id}
                municipality={data.municipality.id}
              >
                Ver producción y cálculo del rendimiento
              </EvidenceLink>
              <button className="button primary" onClick={() => select(c)}>
                Hacer cuentas con este cultivo <IoArrowForward />
              </button>
            </article>
          ))}
      </div>
      {!candidates.length && (
        <div className="empty-state">
          <h3>No encontramos ese cultivo en la referencia municipal</h3>
          <p>
            Prueba otro nombre. La ausencia en EVA no significa que el terreno
            no sea apto.
          </p>
        </div>
      )}
      {candidates.length > 9 && (
        <button
          className="button secondary show-more"
          onClick={() => setMore(!more)}
        >
          {more
            ? "Mostrar menos"
            : `Ver los ${candidates.length} sistemas reportados`}
        </button>
      )}
      <div className="regional-context">
        <section className="panel">
          <h3>Lo que sabemos del suelo de la zona</h3>
          {soil ? (
            <>
              <p>
                AGROSAVIA dispone de {number(soil.samples)} muestras de
                laboratorio identificadas con este municipio.
              </p>
              {soil.ph_median !== null && (
                <div className="soil-stat">
                  <strong>{number(soil.ph_median)}</strong>
                  <span>
                    pH mediano de {number(soil.ph_samples)} muestras
                    <br />
                    La mitad central: {number(soil.ph_low!)} a{" "}
                    {number(soil.ph_high!)}.
                  </span>
                </div>
              )}
              {soil.oldest && soil.newest && (
                <p className="privacy-note">
                  Análisis entre {dateLabel(soil.oldest)} y{" "}
                  {dateLabel(soil.newest)}.
                </p>
              )}
              <EvidenceLink
                id={soil.document_id}
                municipality={data.municipality.id}
              >
                Ver origen y resumen de las muestras
              </EvidenceLink>
            </>
          ) : (
            <p>
              No encontramos muestras de laboratorio vinculadas a este
              municipio.
            </p>
          )}
          <p className="inline-note">
            Son muestras enviadas a un laboratorio, sin ubicación exacta de
            parcela. No describen necesariamente el suelo de tu finca ni se usan
            para indicar fertilización.
          </p>
        </section>
        <section className="panel">
          <h3>Antes de elegir, confirma tres cosas</h3>
          <ol className="plain-steps">
            <li>
              Que las condiciones de tu lote correspondan con el sistema y la
              variedad del mapa.
            </li>
            <li>
              Que tengas agua, mano de obra y dinero durante el período de
              producción.
            </li>
            <li>
              Que exista un comprador alcanzable para la calidad y cantidad que
              esperas cosechar.
            </li>
          </ol>
          <p>
            Los mapas orientan la planificación regional. Aptitud y rentabilidad
            se consultan por separado.
          </p>
          <a
            href="https://sipra.upra.gov.co/"
            target="_blank"
            rel="noreferrer"
            className="evidence-link"
          >
            Explorar el mapa completo en SIPRA ↗
          </a>
        </section>
      </div>
    </>
  );
}
