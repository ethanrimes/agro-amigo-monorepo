"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useFarm } from "@/components/planning/FarmContext";
import { FarmEditor } from "@/components/planning/FarmEditor";
import { CropOptions } from "@/components/planning/CropOptions";
import { CropBudget } from "@/components/planning/CropBudget";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { profileFor } from "@/lib/farm-types";
import type { FarmData, CropReference } from "@/lib/planning-types";
function Planner() {
  const context = useFarm(),
    { ready } = context,
    params = useSearchParams(),
    [tab, setTab] = useState(
      params.get("tab") === "budget" ? "budget" : "crops",
    ),
    [chosen, setChosen] = useState("");
  const record =
    context.farms.find((f) => f.id === params.get("farm")) ||
    context.activeFarm;
  const managed =
    record?.crops.find(
      (c) => c.id === (params.get("crop") || record.selectedCropId),
    ) || record?.crops[0];
  const farm = record ? profileFor(record, managed?.id) : context.farm;
  useEffect(() => {
    if (record) context.selectFarm(record.id);
  }, [record?.id, context.activeFarm?.id]);
  const info = useData<FarmData>(
    ready && farm.municipalityId
      ? "/api/planning/farm?id=" + farm.municipalityId
      : null,
  );
  const crop =
    info.data?.crops.find((c) => c.crop_code === (chosen || farm.cropCode)) ||
    (!chosen && managed?.cropCode.startsWith("manual-")
      ? ({
          crop_code: managed.cropCode,
          crop: managed.name,
          variety: managed.variety || managed.name,
          reference_year: 0,
          cycle: "Transitorio",
          physical_state: managed.physicalState,
          planted_ha: 0,
          harvested_ha: 0,
          production_t: 0,
          yield_kg_ha: null,
          document_id: "",
          source_rows: [],
        } as CropReference)
      : info.data?.crops[0]);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PLANEA TU PRÓXIMA COSECHA</span>
          <h1>¿Qué sembrar y cuánto puede dejar?</h1>
          <p>
            {info.data
              ? info.data.municipality.name +
                ", " +
                info.data.municipality.department
              : "Elige tu ubicación para empezar con referencias locales."}
          </p>
        </div>
        {farm.municipalityId && (
          <Link className="button secondary" href="/farm">
            Ver mis fincas
          </Link>
        )}
      </div>
      {!ready ? (
        <p role="status">Cargando tu ubicación…</p>
      ) : !farm.municipalityId ? (
        <FarmEditor />
      ) : (
        <>
          <div
            className="planning-tabs"
            role="tablist"
            aria-label="Herramientas para planear"
          >
            <button
              role="tab"
              aria-selected={tab === "crops"}
              onClick={() => setTab("crops")}
            >
              1. Explorar cultivos
            </button>
            <button
              role="tab"
              aria-selected={tab === "budget"}
              onClick={() => setTab("budget")}
            >
              2. Presupuesto y cosecha
            </button>
          </div>
          {info.loading ? (
            <div className="panel" role="status">
              Consultando producción, aptitud y calendarios…
            </div>
          ) : info.error ? (
            <ErrorState message={info.error} retry={info.retry} />
          ) : (
            info.data && (
              <div role="tabpanel">
                {tab === "crops" ? (
                  <CropOptions
                    data={info.data}
                    select={(c) => {
                      setChosen(c.crop_code);
                      setTab("budget");
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  />
                ) : crop ? (
                  <>
                    <label className="form-field budget-crop-picker">
                      Cultivo y sistema del escenario
                      <select
                        value={crop.crop_code}
                        onChange={(e) => setChosen(e.target.value)}
                      >
                        {!info.data.crops.some(
                          (c) => c.crop_code === crop.crop_code,
                        ) && (
                          <option value={crop.crop_code}>{crop.variety}</option>
                        )}
                        {info.data.crops.map((c) => (
                          <option key={c.crop_code} value={c.crop_code}>
                            {c.variety}
                          </option>
                        ))}
                      </select>
                    </label>
                    <CropBudget
                      key={
                        (record?.id || farm.municipalityId) +
                        "-" +
                        (managed?.id || "") +
                        "-" +
                        crop.crop_code
                      }
                      crop={crop}
                      data={info.data}
                      farm={farm}
                      managed={
                        managed?.cropCode === crop.crop_code
                          ? managed
                          : undefined
                      }
                      scenarioKey={
                        record
                          ? "agroamigo-scenarios-" + record.id
                          : "agroamigo-scenarios-v1"
                      }
                      onApply={
                        record && managed?.cropCode === crop.crop_code
                          ? (plan) =>
                              context.saveCrop(record.id, {
                                ...managed,
                                area: String(plan.areaHa),
                                yieldKgHa: String(plan.yieldKgHa),
                                budget: plan,
                              })
                          : undefined
                      }
                    />
                    {record && (
                      <Link
                        className="button secondary"
                        href={"/farm/" + record.id}
                      >
                        Ver las cuentas de {record.profile.name} →
                      </Link>
                    )}
                  </>
                ) : (
                  <div className="empty-state">
                    <h2>Sin producción municipal disponible</h2>
                    <p>
                      Prueba otro municipio desde Mi finca. No hay datos
                      suficientes para precargar este escenario.
                    </p>
                  </div>
                )}
              </div>
            )
          )}
        </>
      )}
    </>
  );
}
export default function PlanPage() {
  return (
    <Suspense fallback={<p>Preparando tus herramientas…</p>}>
      <Planner />
    </Suspense>
  );
}
