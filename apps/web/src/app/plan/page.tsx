"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useFarm } from "@/components/planning/FarmContext";
import { CropReferences } from "@/components/planning/CropReferences";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import type { FarmData, Municipality } from "@/lib/planning-types";

function References() {
  const context = useFarm(),
    params = useSearchParams();
  const farmId = params.get("farm");
  const record = farmId
    ? context.farms.find((f) => f.id === farmId)
    : context.activeFarm;
  const unknownFarm = !!farmId && !record;
  const [selectedMunicipality, setMunicipality] = useState<string | null>(null);
  const [selectedCrop, setCrop] = useState<string | null>(null);
  const municipality =
    selectedMunicipality ??
    params.get("municipality") ??
    record?.profile.municipalityId ??
    "";
  const managed = record?.crops.find(
    (c) => c.id === (params.get("crop") || record.selectedCropId),
  );
  const requestedCrop =
    selectedCrop ?? params.get("crop") ?? managed?.cropCode ?? "";
  const places = useData<Municipality[]>("/api/planning/municipalities");
  const info = useData<FarmData>(
    context.ready && municipality && !unknownFarm
      ? "/api/planning/farm?id=" + encodeURIComponent(municipality)
      : null,
  );
  const crop =
    info.data?.crops.find(
      (c) =>
        c.crop_code ===
        (managed?.id === requestedCrop ? managed.cropCode : requestedCrop),
    ) || (!requestedCrop ? info.data?.crops[0] : undefined);
  return (
    <>
      <header className="page-heading">
        <div>
          <span className="eyebrow">REFERENCIAS AGRÍCOLAS</span>
          <h1>Cultivos, calendarios y fuentes</h1>
          <p>
            Consulta los datos publicados para el municipio y el cultivo. Cada
            referencia conserva su año y alcance.
          </p>
        </div>
        <Link className="button secondary" href="/farm">
          Volver a Mi finca
        </Link>
      </header>
      {!context.ready ? (
        <p role="status">Leyendo las ubicaciones guardadas…</p>
      ) : unknownFarm ? (
        <section className="panel">
          <h2>No encontramos esa finca en este dispositivo</h2>
          <p>El enlace no modifica ni sustituye tus registros guardados.</p>
        </section>
      ) : (
        <>
          {params.get("tab") === "budget" && (
            <p className="inline-note">
              Este enlace ahora muestra las referencias publicadas. Los
              presupuestos y registros anteriores se conservan en este
              dispositivo.
            </p>
          )}
          <section className="panel">
            <div className="form-grid">
              <label className="form-field">
                Municipio de referencia
                <select
                  value={municipality}
                  onChange={(e) => {
                    setMunicipality(e.target.value);
                    setCrop("");
                  }}
                >
                  <option value="">Elige un municipio</option>
                  {places.data?.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}, {m.department}
                    </option>
                  ))}
                </select>
              </label>
              {info.data && (
                <label className="form-field">
                  Cultivo y sistema de referencia
                  <select
                    value={crop?.crop_code || ""}
                    onChange={(e) => setCrop(e.target.value)}
                  >
                    <option value="">Elige un cultivo reportado</option>
                    {info.data.crops.map((c) => (
                      <option key={c.crop_code} value={c.crop_code}>
                        {c.variety} · {c.physical_state}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            <p className="privacy-note">
              Cambiar estas referencias no cambia el pin, el municipio ni los
              cultivos guardados de tu finca.
            </p>
          </section>
          {places.error && (
            <ErrorState message={places.error} retry={places.retry} />
          )}
          {info.loading && (
            <p role="status">Consultando las fuentes del municipio…</p>
          )}
          {info.error && <ErrorState message={info.error} retry={info.retry} />}
          {info.data &&
            (crop ? (
              <CropReferences
                key={info.data.municipality.id + "-" + crop.crop_code}
                data={info.data}
                crop={crop}
              />
            ) : (
              <p className="inline-note">
                No hay una referencia EVA que corresponda al cultivo solicitado.
                Elige uno de los sistemas reportados; no se sustituyó tu cultivo
                guardado.
              </p>
            ))}
        </>
      )}
    </>
  );
}
function LinkedReferences() {
  const params = useSearchParams();
  return <References key={params.toString()} />;
}
export default function PlanPage() {
  return (
    <Suspense fallback={<p>Cargando referencias…</p>}>
      <LinkedReferences />
    </Suspense>
  );
}
