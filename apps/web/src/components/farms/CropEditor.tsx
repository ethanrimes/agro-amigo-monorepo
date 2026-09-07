"use client";
import { useState } from "react";
import { SearchBox } from "@/components/ui/SearchBox";
import { useFarm } from "@/components/planning/FarmContext";
import type { FarmData } from "@/lib/planning-types";
import {
  allocatedArea,
  cropFromProfile,
  type FarmRecord,
  type ManagedCrop,
} from "@/lib/farm-types";
import { number } from "@/lib/market-types";
export function CropEditor({
  record,
  data,
  initial,
  onSaved,
}: {
  record: FarmRecord;
  data: FarmData;
  initial?: ManagedCrop;
  onSaved: () => void;
}) {
  const { saveCrop } = useFarm(),
    [draft, setDraft] = useState<ManagedCrop>(
      initial || {
        ...cropFromProfile(record.profile),
        cropCode: "",
        name: "",
        variety: "",
        area: String(Math.max(0, +record.profile.area - allocatedArea(record))),
        yieldKgHa: "",
        stage: "planning",
      },
    ),
    [search, setSearch] = useState(
      data.crops.find((c) => c.crop_code === initial?.cropCode)?.variety ||
        initial?.name ||
        "",
    ),
    [error, setError] = useState("");
  const patch = (key: keyof ManagedCrop, value: string | boolean) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const selected = data.crops.find((c) => c.crop_code === draft.cropCode);
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !search.trim() ||
      !draft.area ||
      !Number.isFinite(+draft.area) ||
      +draft.area <= 0 ||
      +draft.yieldKgHa < 0 ||
      (draft.yieldKgHa !== "" && !Number.isFinite(+draft.yieldKgHa))
    ) {
      setError(
        "Ingresa el cultivo, un área mayor a cero y un rendimiento válido.",
      );
      return;
    }
    const changed =
      initial &&
      (initial.area !== draft.area ||
        initial.yieldKgHa !== draft.yieldKgHa ||
        initial.cropCode !== draft.cropCode ||
        initial.planYear !== draft.planYear ||
        initial.physicalState !== draft.physicalState);
    const next = {
      ...draft,
      cropCode: draft.cropCode || "manual-" + draft.id,
      name: selected?.crop || search.trim(),
      budget: changed ? undefined : draft.budget,
    };
    if (!saveCrop(record.id, next)) {
      setError(
        "La suma de las áreas de los cultivos supera el área total de la finca. Revisa las hectáreas.",
      );
      return;
    }
    onSaved();
  };
  return (
    <form className="crop-editor" onSubmit={save}>
      <p>
        Área de la finca: <strong>{number(+record.profile.area)} ha</strong> ·
        Asigna el área de cada cultivo sin contar dos veces el mismo terreno.
      </p>
      <div className="form-grid">
        <div className="form-field">
          <span>Cultivo o sistema</span>
          <SearchBox
            label="Cultivo o sistema"
            value={search}
            onChange={(value) => {
              setSearch(value);
              setDraft((d) => ({ ...d, cropCode: "", name: value }));
            }}
            options={data.crops.map((c) => ({
              id: c.crop_code,
              label: c.variety,
              detail: c.physical_state,
            }))}
            onSelect={(o) => {
              const c = data.crops.find((c) => c.crop_code === o.id)!;
              setDraft((d) => ({
                ...d,
                cropCode: c.crop_code,
                name: c.crop,
                physicalState: c.physical_state,
              }));
            }}
          />
          <small>
            Puedes escribir un cultivo aunque no tenga referencias públicas.
          </small>
        </div>
        <label className="form-field">
          Variedad o nombre del lote
          <input
            value={draft.variety}
            maxLength={100}
            onChange={(e) => patch("variety", e.target.value)}
            placeholder="Ej. Castillo · lote de arriba"
          />
        </label>
        <label className="form-field">
          Hectáreas de este cultivo
          <input
            required
            type="number"
            min="0.01"
            max={record.profile.area}
            step="any"
            value={draft.area}
            onChange={(e) => patch("area", e.target.value)}
          />
        </label>
        <label className="form-field">
          Rendimiento esperado (kg/ha)
          <input
            type="number"
            min="0"
            max="1000000"
            step="any"
            value={draft.yieldKgHa}
            onChange={(e) => patch("yieldKgHa", e.target.value)}
            placeholder="Lo puedes completar después"
          />
          <small>
            Para el año o ciclo que presupuestarás, antes de pérdidas.
          </small>
        </label>
        <label className="form-field">
          Estado del producto
          <input
            value={draft.physicalState}
            onChange={(e) => patch("physicalState", e.target.value)}
            maxLength={100}
            placeholder="Ej. pergamino seco, grano seco, fresco"
          />
        </label>
        <label className="form-field">
          Año de estas cuentas
          <input
            required
            type="number"
            min="2020"
            max="2100"
            step="1"
            value={draft.planYear}
            onChange={(e) => patch("planYear", e.target.value)}
          />
        </label>
        <label className="form-field">
          Momento del cultivo
          <select
            value={draft.stage}
            onChange={(e) => patch("stage", e.target.value)}
          >
            <option value="planning">Estoy planeando</option>
            <option value="planting">Siembra o establecimiento</option>
            <option value="growth">Crecimiento</option>
            <option value="flowering">Floración</option>
            <option value="harvest">Cosecha o poscosecha</option>
          </select>
        </label>
        <label className="form-field">
          Fecha de siembra
          <input
            type="date"
            value={draft.plantingDate}
            onChange={(e) => patch("plantingDate", e.target.value)}
          />
        </label>
        <label className="form-field">
          Floración observada (opcional)
          <input
            type="date"
            value={draft.floweringDate}
            onChange={(e) => patch("floweringDate", e.target.value)}
          />
        </label>
      </div>
      <label className="check-field">
        <input
          type="checkbox"
          checked={draft.irrigation}
          onChange={(e) => patch("irrigation", e.target.checked)}
        />{" "}
        Tengo acceso a riego para este cultivo
      </label>
      {initial?.budget && (
        <p className="inline-note">
          Si cambias el cultivo, el área, el rendimiento, el estado del producto
          o el año, tendrás que recalcular su presupuesto.
        </p>
      )}
      {error && (
        <p role="alert" className="invalid-input">
          {error}
        </p>
      )}
      <button className="button primary" type="submit">
        Guardar cultivo
      </button>
    </form>
  );
}
