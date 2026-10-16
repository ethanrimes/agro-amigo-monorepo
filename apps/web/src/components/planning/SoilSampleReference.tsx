import type { FarmData } from "@/lib/planning-types";
import { number, dateLabel } from "@/lib/market-types";
import { EvidenceLink } from "./EvidenceLink";

/** Municipality laboratory samples are distinct from a farm's mapped soil. */
export function SoilSampleReference({ data }: { data: FarmData }) {
  const soil = data.soil;
  return (
    <section className="panel">
      <span className="eyebrow">
        {data.municipality.name}, {data.municipality.department} · AGROSAVIA
      </span>
      <h3>Muestras de suelo del municipio</h3>
      {soil ? (
        <>
          <p>
            AGROSAVIA dispone de {number(soil.samples)} muestras de laboratorio
            identificadas con este municipio.
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
              Análisis entre {dateLabel(soil.oldest)} y {dateLabel(soil.newest)}.
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
        <p>No encontramos muestras de laboratorio vinculadas a este municipio.</p>
      )}
      <p className="inline-note">
        Son muestras enviadas a un laboratorio, sin ubicación exacta de parcela.
        No describen necesariamente el suelo de tu finca ni se usan para indicar
        fertilización.
      </p>
    </section>
  );
}
