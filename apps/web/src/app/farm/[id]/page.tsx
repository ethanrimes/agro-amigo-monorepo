"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  IoAddOutline,
  IoCreateOutline,
  IoDownloadOutline,
  IoLocationOutline,
} from "react-icons/io5";
import { useFarm } from "@/components/planning/FarmContext";
import { FarmEditor } from "@/components/planning/FarmEditor";
import { WeeklyPlan } from "@/components/planning/WeeklyPlan";
import { FarmMap } from "@/components/farms/FarmMap";
import { CropEditor } from "@/components/farms/CropEditor";
import {
  FarmFinancials,
  CropBenchmarks,
  budgetLink,
} from "@/components/farms/FarmFinancials";
import { Overlay } from "@/components/ui/Overlay";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import {
  allocatedArea,
  hasPin,
  profileFor,
  type ManagedCrop,
} from "@/lib/farm-types";
import { photoFor } from "@/lib/images";
import { number } from "@/lib/market-types";
import type { FarmData } from "@/lib/planning-types";
export default function FarmDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    router = useRouter(),
    context = useFarm(),
    { farms, ready, selectFarm, selectCrop } = context;
  const record = farms.find((f) => f.id === id),
    [tab, setTab] = useState("summary"),
    [editing, setEditing] = useState(false),
    [cropEdit, setCropEdit] = useState<ManagedCrop | "new" | null>(null);
  const data = useData<FarmData>(
    record ? "/api/planning/farm?id=" + record.profile.municipalityId : null,
  );
  useEffect(() => {
    if (ready && record) selectFarm(id);
  }, [id, ready, context.activeFarm?.id]);
  if (!ready) return <p role="status">Cargando tu finca…</p>;
  if (!record)
    return (
      <section className="empty-state">
        <h1>No encontramos esta finca en el dispositivo</h1>
        <Link className="button primary" href="/farm">
          Ver mis fincas
        </Link>
      </section>
    );
  const crop =
      record.crops.find((c) => c.id === record.selectedCropId) ||
      record.crops[0],
    profile = profileFor(record),
    area = allocatedArea(record);
  const exportFarm = () => {
    const json = JSON.stringify(
      {
        format: "agroamigo-farm",
        version: 2,
        exportedAt: new Date().toISOString(),
        farm: record,
      },
      null,
      2,
    );
    if (/AgroAmigo(Android|IOS)\//.test(navigator.userAgent)) {
      window.location.href =
        "agroamigo-export://scenario?data=" + encodeURIComponent(json);
      return;
    }
    const url = URL.createObjectURL(
        new Blob([json], { type: "application/json" }),
      ),
      a = document.createElement("a");
    a.href = url;
    a.download = "finca-agroamigo-" + id + ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <>
      <Link className="back-link" href="/farm">
        ← Mis fincas
      </Link>
      <div className="catalog-heading farm-detail-heading">
        <div>
          <span className="eyebrow">MI FINCA</span>
          <h1>{record.profile.name}</h1>
          <p>
            <IoLocationOutline />
            {data.data
              ? data.data.municipality.name +
                ", " +
                data.data.municipality.department
              : "Municipio registrado"}
          </p>
        </div>
        <div className="farm-header-actions">
          <button className="button secondary" onClick={() => setEditing(true)}>
            <IoCreateOutline />
            Editar finca
          </button>
          <button className="button secondary" onClick={exportFarm}>
            <IoDownloadOutline />
            Descargar mis datos
          </button>
        </div>
      </div>
      {context.storageError && (
        <p role="alert" className="inline-warning">
          {context.storageError}
        </p>
      )}
      {farms.length > 1 && (
        <label className="form-field farm-switcher">
          Finca que estás consultando
          <select
            value={id}
            onChange={(e) => router.push("/farm/" + e.target.value)}
          >
            {farms.map((f) => (
              <option key={f.id} value={f.id}>
                {f.profile.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="farm-location-summary">
        <section className="panel farm-land-summary">
          <h2>Tu finca de un vistazo</h2>
          <div className="farm-land-number">
            <strong>{number(+record.profile.area)}</strong>
            <span>hectáreas totales</span>
          </div>
          <div
            className="farm-area-bar"
            aria-label={number(area) + " hectáreas asignadas a cultivos"}
          >
            {record.crops.map((c, i) => (
              <span
                key={c.id}
                style={{
                  width: (+c.area / +record.profile.area) * 100 + "%",
                  background: ["#1f6548", "#75a367", "#c09347", "#548986"][
                    i % 4
                  ],
                }}
              />
            ))}
          </div>
          <p>
            {number(area)} ha en {record.crops.length} cultivos o lotes ·{" "}
            {number(Math.max(0, +record.profile.area - area))} ha por asignar
          </p>
          <button className="text-button" onClick={() => setTab("crops")}>
            Ver y organizar cultivos →
          </button>
        </section>
        <section className="panel farm-map-panel">
          <div className="section-heading">
            <h2>Ubicación de la finca</h2>
            <button className="text-button" onClick={() => setEditing(true)}>
              Ajustar pin
            </button>
          </div>
          <FarmMap
            key={id}
            name={record.profile.name}
            point={
              hasPin(record.profile)
                ? {
                    latitude: +record.profile.latitude,
                    longitude: +record.profile.longitude,
                  }
                : null
            }
            center={data.data?.municipality}
          />
          <p className="field-help">
            {hasPin(record.profile)
              ? `Pin guardado: ${(+record.profile.latitude).toFixed(5)}, ${(+record.profile.longitude).toFixed(5)}${record.profile.locationMethod === "gps" ? " · GPS" : ""}.`
              : "Falta guardar el pin. El mapa muestra el municipio como referencia."}{" "}
            No representa linderos.
          </p>
        </section>
      </div>
      <div
        className="farm-section-tabs"
        role="tablist"
        aria-label="Secciones de la finca"
      >
        {[
          ["summary", "Mis cuentas"],
          ["crops", "Mis cultivos"],
          ["weather", "Clima y labores"],
        ].map(([key, label]) => (
          <button
            role="tab"
            key={key}
            aria-selected={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {data.loading ? (
        <p role="status">Consultando referencias de tu zona…</p>
      ) : data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : (
        data.data && (
          <div role="tabpanel">
            {tab === "summary" ? (
              <>
                <FarmFinancials record={record} data={data.data} />
                {crop && (
                  <>
                    <label className="form-field farm-switcher">
                      Cultivo para comparar referencias
                      <select
                        value={crop.id}
                        onChange={(e) => selectCrop(e.target.value)}
                      >
                        {record.crops.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.variety ||
                              data.data!.crops.find(
                                (r) => r.crop_code === c.cropCode,
                              )?.variety ||
                              c.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <CropBenchmarks
                      record={record}
                      crop={crop}
                      data={data.data}
                    />
                  </>
                )}
              </>
            ) : tab === "weather" ? (
              <>
                {crop && (
                  <label className="form-field farm-switcher">
                    Cultivo para las labores
                    <select
                      value={crop.id}
                      onChange={(e) => selectCrop(e.target.value)}
                    >
                      {record.crops.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.variety ||
                            data.data!.crops.find(
                              (r) => r.crop_code === c.cropCode,
                            )?.variety ||
                            c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <WeeklyPlan
                  key={id + "-" + crop?.id}
                  farm={profile}
                  data={data.data}
                  storageKey={id + "-" + (crop?.id || "general")}
                />
              </>
            ) : (
              <>
                <div className="section-heading">
                  <div>
                    <h2>Los cultivos de {record.profile.name}</h2>
                    <p>
                      Registra las áreas y prepara las cuentas de cada cultivo.
                    </p>
                  </div>
                  <button
                    className="button primary"
                    onClick={() => setCropEdit("new")}
                  >
                    <IoAddOutline />
                    Agregar cultivo
                  </button>
                </div>
                <div className="managed-crop-grid">
                  {record.crops.map((c) => {
                    const ref = data.data!.crops.find(
                        (r) => r.crop_code === c.cropCode,
                      ),
                      name = c.variety || ref?.variety || c.name,
                      pic = photoFor(ref?.crop || c.name);
                    return (
                      <article className="managed-crop-card" key={c.id}>
                        <img src={pic.src} alt={pic.alt} />
                        <div>
                          <span className="eyebrow">
                            {c.planYear} ·{" "}
                            {c.stage === "planning"
                              ? "En planeación"
                              : c.stage === "harvest"
                                ? "En cosecha"
                                : "Cultivo registrado"}
                          </span>
                          <h3>{name}</h3>
                          <p>
                            <strong>{number(+c.area)} ha</strong> ·{" "}
                            {c.yieldKgHa
                              ? number(+c.yieldKgHa) + " kg/ha esperados"
                              : "Rendimiento por completar"}
                          </p>
                          <small>
                            {c.physicalState || ref?.physical_state}
                          </small>
                          <div className="form-actions">
                            <Link
                              className="button primary"
                              href={budgetLink(id, c.id)}
                            >
                              {c.budget
                                ? "Revisar presupuesto"
                                : "Hacer presupuesto"}{" "}
                              →
                            </Link>
                            <button
                              className="button secondary"
                              onClick={() => setCropEdit(c)}
                            >
                              Editar cultivo
                            </button>
                          </div>
                          <button
                            className="text-button danger-link"
                            onClick={() => {
                              if (
                                window.confirm(
                                  "¿Quitar este cultivo y su presupuesto de la finca?",
                                )
                              )
                                context.removeCrop(id, c.id);
                            }}
                          >
                            Quitar cultivo
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
                {!record.crops.length && (
                  <div className="finance-empty">
                    <h3>Tu primer cultivo empieza aquí</h3>
                    <p>Agrega su nombre y las hectáreas que ocupa.</p>
                  </div>
                )}
                <Link className="button secondary" href="/plan">
                  Explorar qué podría sembrar en esta zona →
                </Link>
              </>
            )}
          </div>
        )
      )}
      <div className="farm-bottom-links">
        <Link href="/offers">Comparar ofertas de venta o compra →</Link>
        <button
          className="text-button danger-link"
          onClick={() => {
            if (
              window.confirm(
                "¿Eliminar esta finca y sus cultivos de este dispositivo? Descarga primero una copia si la necesitas.",
              )
            ) {
              context.removeFarm(id);
              router.replace("/farm");
            }
          }}
        >
          Eliminar finca
        </button>
      </div>
      {editing && (
        <Overlay
          title="Editar finca y ubicación"
          className="farm-editor-overlay"
          onClose={() => setEditing(false)}
        >
          <div className="document-workspace">
            <FarmEditor
              initial={record.profile}
              minimumArea={area}
              locationOnly
              onCommit={(p) => {
                context.updateFarm(id, p);
                window.history.back();
              }}
            />
          </div>
        </Overlay>
      )}
      {cropEdit && data.data && (
        <Overlay
          title={cropEdit === "new" ? "Agregar cultivo" : "Editar cultivo"}
          className="crop-editor-overlay"
          onClose={() => setCropEdit(null)}
        >
          <div className="document-workspace">
            <CropEditor
              record={record}
              data={data.data}
              initial={cropEdit === "new" ? undefined : cropEdit}
              onSaved={() => window.history.back()}
            />
          </div>
        </Overlay>
      )}
    </>
  );
}
