"use client";
import { useEffect, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { EMPTY_FARM, useFarm } from "./FarmContext";
import type { FarmData, FarmProfile, Municipality } from "@/lib/planning-types";
import { FarmLocation } from "@/components/farms/FarmLocation";
import { fold } from "@/lib/planning-math";
export function FarmEditor({
  onSaved,
  initial,
  onCommit,
  minimumArea = 0,
  locationOnly = false,
}: {
  onSaved?: () => void;
  initial?: FarmProfile;
  onCommit?: (p: FarmProfile) => void;
  minimumArea?: number;
  locationOnly?: boolean;
}) {
  const context = useFarm(),
    farm = initial || context.farm,
    save = onCommit || context.save;
  const [draft, setDraft] = useState(farm),
    [department, setDepartment] = useState(""),
    [problem, setProblem] = useState("");
  const places = useData<Municipality[]>("/api/planning/municipalities");
  const selected = places.data?.find((m) => m.id === draft.municipalityId);
  const local = useData<FarmData>(
    draft.municipalityId
      ? "/api/planning/farm?id=" + draft.municipalityId
      : null,
  );
  useEffect(() => {
    if (selected && selected.department !== department)
      setDepartment(selected.department);
  }, [selected, department]);
  const patch = (key: keyof FarmProfile, value: string | boolean) =>
    setDraft((d) => ({
      ...d,
      [key]: value,
      ...(["latitude", "longitude"].includes(key)
        ? { locationMethod: "manual", locationAccuracy: "" }
        : {}),
    }));
  const departments = [
    ...new Set(places.data?.map((m) => m.department) || []),
  ].sort((a, b) => a.localeCompare(b, "es"));
  const crop = local.data?.crops.find((c) => c.crop_code === draft.cropCode);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const lat = draft.latitude.trim(),
      lon = draft.longitude.trim();
    if (
      !selected ||
      !draft.area ||
      !Number.isFinite(+draft.area) ||
      +draft.area <= 0 ||
      +draft.area > 100000
    ) {
      setProblem("Selecciona un municipio y un área mayor a cero.");
      return;
    }
    if (
      (lat || lon) &&
      (!lat ||
        !lon ||
        !Number.isFinite(+lat) ||
        !Number.isFinite(+lon) ||
        +lat < -5 ||
        +lat > 14 ||
        +lon < -82 ||
        +lon > -66)
    ) {
      setProblem(
        "Completa ambas coordenadas con un punto ubicado en Colombia.",
      );
      return;
    }
    if (
      draft.elevation &&
      (!Number.isFinite(+draft.elevation) ||
        +draft.elevation < 0 ||
        +draft.elevation > 6000)
    ) {
      setProblem("La altitud debe estar entre 0 y 6.000 metros.");
      return;
    }
    if (+draft.area + 1e-8 < minimumArea) {
      setProblem(
        `Los cultivos ocupan ${minimumArea} ha. El área de la finca no puede ser menor.`,
      );
      return;
    }
    save({
      ...draft,
      cropCode: crop?.crop_code || "",
      name: draft.name.trim() || "Mi finca",
    });
    setProblem("");
    onSaved?.();
  };
  return (
    <section className="panel farm-editor">
      <div className="section-heading">
        <div>
          <span className="eyebrow">EMPECEMOS POR TU UBICACIÓN</span>
          <h2>
            {farm.municipalityId
              ? "Ajusta los datos de tu finca"
              : "La información que le sirve a tu finca"}
          </h2>
          <p>
            El municipio permite consultar clima, cultivos y referencias
            locales.
          </p>
        </div>
      </div>
      {places.error ? (
        <ErrorState message={places.error} retry={places.retry} />
      ) : (
        <form onSubmit={submit}>
          <FarmLocation
            draft={draft}
            places={places.data || []}
            onChange={(p) => setDraft((d) => ({ ...d, ...p }))}
          />
          <div className="form-grid">
            <label className="form-field">
              Departamento
              <select
                required
                aria-label="Departamento"
                value={department}
                onChange={(e) => {
                  setDepartment(e.target.value);
                  setDraft((d) => ({
                    ...d,
                    municipalityId: "",
                    cropCode: "",
                  }));
                }}
              >
                <option value="">
                  {places.loading
                    ? "Cargando municipios…"
                    : "Selecciona tu departamento"}
                </option>
                {departments.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              Municipio
              <select
                required
                aria-label="Municipio"
                value={draft.municipalityId}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    municipalityId: e.target.value,
                    cropCode: "",
                  }))
                }
              >
                <option value="">Selecciona tu municipio</option>
                {places.data
                  ?.filter((m) => m.department === department)
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          {draft.municipalityId && (
            <>
              <div className="form-grid">
                <label className="form-field">
                  Nombre de tu finca
                  <input
                    maxLength={80}
                    value={draft.name}
                    onChange={(e) => patch("name", e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Área total de la finca (hectáreas)
                  <input
                    type="number"
                    step="any"
                    min="0.01"
                    max="100000"
                    required
                    value={draft.area}
                    onChange={(e) => patch("area", e.target.value)}
                  />
                </label>
                {!locationOnly && (
                  <label className="form-field">
                    Cultivo principal
                    <select
                      aria-label="Cultivo principal"
                      value={draft.cropCode}
                      onChange={(e) => patch("cropCode", e.target.value)}
                    >
                      <option value="">Todavía estoy decidiendo</option>
                      {local.data?.crops.map((c) => (
                        <option key={c.crop_code} value={c.crop_code}>
                          {c.variety}
                        </option>
                      ))}
                    </select>
                    <small>Opciones reportadas en el municipio por UPRA.</small>
                  </label>
                )}
                {!locationOnly && (
                  <label className="form-field">
                    Momento del cultivo
                    <select
                      value={draft.stage}
                      onChange={(e) => patch("stage", e.target.value)}
                    >
                      <option value="planning">Estoy planeando</option>
                      <option value="planting">
                        Siembra o establecimiento
                      </option>
                      <option value="growth">Crecimiento</option>
                      <option value="flowering">Floración</option>
                      <option value="harvest">Cosecha o poscosecha</option>
                    </select>
                  </label>
                )}
              </div>
              {!locationOnly && (
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={draft.irrigation}
                    onChange={(e) => patch("irrigation", e.target.checked)}
                  />{" "}
                  Tengo acceso a riego
                </label>
              )}
              <details className="source-explanation">
                <summary>
                  {locationOnly
                    ? "Altitud (opcional)"
                    : "Fechas, variedad y altitud (opcional)"}
                </summary>
                <div className="form-grid">
                  {!locationOnly && (
                    <>
                      <label className="form-field">
                        Variedad que tienes
                        <input
                          placeholder="Por ejemplo: Castillo o Alhaja"
                          value={draft.variety}
                          onChange={(e) => patch("variety", e.target.value)}
                          maxLength={100}
                        />
                      </label>
                      <label className="form-field">
                        Fecha de siembra o establecimiento
                        <input
                          type="date"
                          value={draft.plantingDate}
                          onChange={(e) =>
                            patch("plantingDate", e.target.value)
                          }
                        />
                      </label>
                      {fold(crop?.crop || "") === "cafe" && (
                        <label className="form-field">
                          Floración principal observada
                          <input
                            type="date"
                            value={draft.floweringDate}
                            onChange={(e) =>
                              patch("floweringDate", e.target.value)
                            }
                          />
                          <small>
                            Se usa para estimar la ventana de cosecha del café.
                          </small>
                        </label>
                      )}
                    </>
                  )}
                  <label className="form-field">
                    Altitud conocida (metros)
                    <input
                      type="number"
                      min="0"
                      max="6000"
                      value={draft.elevation}
                      onChange={(e) => patch("elevation", e.target.value)}
                    />
                  </label>
                </div>
                <p>
                  Sin coordenadas, se usa un punto de referencia del municipio
                  para consultar el clima. La aptitud se presenta a escala
                  municipal.
                </p>
              </details>
            </>
          )}
          {initial && (
            <p className="inline-note">
              Si cambias de municipio, revisa y vuelve a guardar los
              presupuestos de sus cultivos con las nuevas referencias.
            </p>
          )}
          {local.error && <p className="inline-warning">{local.error}</p>}
          {problem && (
            <p role="alert" className="invalid-input">
              {problem}
            </p>
          )}
          <div className="form-actions">
            <button
              className="button primary"
              type="submit"
              disabled={places.loading}
            >
              Guardar mi finca →
            </button>
            {!farm.municipalityId && (
              <button
                type="button"
                disabled={places.loading || !places.data?.length}
                className="button secondary"
                onClick={() => {
                  const p = places.data?.find(
                    (m) => fold(m.name) === "pitalito",
                  );
                  if (p) {
                    save({
                      ...EMPTY_FARM,
                      municipalityId: p.id,
                      cropCode: "2030300",
                      name: "Ejemplo · Pitalito",
                      stage: "harvest",
                    });
                    onSaved?.();
                  }
                }}
              >
                Explorar ejemplo en Pitalito
              </button>
            )}
          </div>
          <p className="privacy-note">
            Tus datos se guardan en este navegador. No necesitas crear una
            cuenta ni subir análisis de suelo.
          </p>
        </form>
      )}
    </section>
  );
}
