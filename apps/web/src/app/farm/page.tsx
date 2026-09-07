"use client";
import { useState } from "react";
import Link from "next/link";
import {
  IoLocationOutline,
  IoCalculatorOutline,
  IoLeafOutline,
  IoSwapHorizontalOutline,
  IoCreateOutline,
} from "react-icons/io5";
import { useFarm } from "@/components/planning/FarmContext";
import { FarmEditor } from "@/components/planning/FarmEditor";
import { WeeklyPlan } from "@/components/planning/WeeklyPlan";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { number } from "@/lib/market-types";
import type { FarmData } from "@/lib/planning-types";
export default function FarmPage() {
  const { farm, ready } = useFarm(),
    [editing, setEditing] = useState(false);
  const info = useData<FarmData>(
    ready && farm.municipalityId
      ? "/api/planning/farm?id=" + farm.municipalityId
      : null,
  );
  if (!ready) return <p role="status">Cargando tu finca…</p>;
  const crop = info.data?.crops.find((c) => c.crop_code === farm.cropCode);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">MI FINCA</span>
          <h1>
            {farm.municipalityId
              ? farm.name
              : "Mejores decisiones, desde tu finca"}
          </h1>
          <p>
            {info.data ? (
              <>
                <IoLocationOutline /> {info.data.municipality.name},{" "}
                {info.data.municipality.department} · {number(+farm.area)} ha{" "}
                {crop ? "· " + crop.variety : ""}
              </>
            ) : (
              "Clima, cultivos y cuentas en un solo lugar."
            )}
          </p>
        </div>
        {farm.municipalityId && (
          <button
            className="button secondary"
            onClick={() => setEditing(!editing)}
          >
            <IoCreateOutline />
            {editing ? "Cerrar edición" : "Editar mi finca"}
          </button>
        )}
      </div>
      {!farm.municipalityId || editing ? (
        <FarmEditor
          key={farm.municipalityId}
          onSaved={() => setEditing(false)}
        />
      ) : (
        <>
          <div className="decision-grid">
            <Link href="/plan" className="decision-card">
              <IoLeafOutline />
              <h3>¿Qué podría sembrar?</h3>
              <p>Explora cultivos con referencias para tu municipio.</p>
              <span>Ver opciones →</span>
            </Link>
            <Link href="/plan?tab=budget" className="decision-card">
              <IoCalculatorOutline />
              <h3>¿Me salen las cuentas?</h3>
              <p>Estima costos, cosecha y precio de equilibrio.</p>
              <span>Hacer mi presupuesto →</span>
            </Link>
            <Link href="/offers" className="decision-card">
              <IoSwapHorizontalOutline />
              <h3>¿Qué oferta me conviene?</h3>
              <p>Compara lo que queda después de los gastos de venta.</p>
              <span>Comparar ofertas →</span>
            </Link>
          </div>
          {info.loading ? (
            <div className="panel" role="status">
              Consultando datos de tu zona…
            </div>
          ) : info.error ? (
            <ErrorState message={info.error} retry={info.retry} />
          ) : (
            info.data && (
              <>
                <WeeklyPlan farm={farm} data={info.data} />
                <section className="farm-source-footnote">
                  <p>
                    Tu ubicación y los cultivos de referencia provienen de datos
                    públicos. Los valores de tu finca se conservan en este
                    navegador.
                  </p>
                  <EvidenceLink id={info.data.municipality.document_id}>
                    Consultar directorio municipal
                  </EvidenceLink>
                </section>
              </>
            )
          )}
        </>
      )}
    </>
  );
}
