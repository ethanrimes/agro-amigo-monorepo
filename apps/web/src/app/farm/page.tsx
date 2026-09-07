"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  IoAddOutline,
  IoLocationOutline,
  IoLeafOutline,
} from "react-icons/io5";
import { useFarm, EMPTY_FARM } from "@/components/planning/FarmContext";
import { FarmEditor } from "@/components/planning/FarmEditor";
import { Overlay } from "@/components/ui/Overlay";
import { useData } from "@/components/marketplace/useData";
import { allocatedArea, hasPin } from "@/lib/farm-types";
import { number } from "@/lib/market-types";
import type { Municipality } from "@/lib/planning-types";
export default function FarmsPage() {
  const { farms, ready, addFarm, storageError } = useFarm(),
    router = useRouter(),
    [adding, setAdding] = useState(false);
  const places = useData<Municipality[]>("/api/planning/municipalities");
  const create = (profile: typeof EMPTY_FARM) => {
    const id = addFarm(profile);
    setAdding(false);
    if (adding) router.replace("/farm/" + id);
    else router.push("/farm/" + id);
  };
  if (!ready) return <p role="status">Cargando tus fincas…</p>;
  return (
    <>
      <div className="catalog-heading">
        <div>
          <span className="eyebrow">MI FINCA</span>
          <h1>Mis fincas</h1>
          <p>Cada finca, con sus cultivos, su ubicación y sus cuentas.</p>
        </div>
        {farms.length > 0 && (
          <button className="button primary" onClick={() => setAdding(true)}>
            <IoAddOutline />
            Agregar finca
          </button>
        )}
      </div>
      {storageError && (
        <p role="alert" className="inline-warning">
          {storageError}
        </p>
      )}
      {!farms.length ? (
        <FarmEditor initial={EMPTY_FARM} onCommit={create} />
      ) : (
        <>
          <div className="farm-overview-strip">
            <span>
              <strong>{farms.length}</strong> fincas
            </span>
            <span>
              <strong>
                {number(farms.reduce((s, f) => s + (+f.profile.area || 0), 0))}
              </strong>{" "}
              hectáreas registradas
            </span>
            <span>
              <strong>{farms.reduce((s, f) => s + f.crops.length, 0)}</strong>{" "}
              cultivos / lotes
            </span>
          </div>
          <div className="farm-cards">
            {farms.map((f) => {
              const place = places.data?.find(
                (p) => p.id === f.profile.municipalityId,
              );
              return (
                <Link className="farm-card" href={"/farm/" + f.id} key={f.id}>
                  <div className="farm-card-photo">
                    <img
                      src="/images/farm.jpg"
                      alt="Paisaje agrícola ilustrativo"
                    />
                    <span>
                      <IoLeafOutline />
                      {f.crops.length} cultivos / lotes
                    </span>
                  </div>
                  <div className="farm-card-body">
                    <h2>{f.profile.name}</h2>
                    <p>
                      <IoLocationOutline />
                      {place
                        ? `${place.name}, ${place.department}`
                        : "Municipio registrado"}
                    </p>
                    <div className="farm-card-facts">
                      <span>
                        <b>{number(+f.profile.area)} ha</b>Área total
                      </span>
                      <span>
                        <b>{number(allocatedArea(f))} ha</b>En tus cultivos
                      </span>
                    </div>
                    <small>
                      {hasPin(f.profile)
                        ? "Ubicación con pin guardada"
                        : "Falta ubicar el pin de esta finca"}
                    </small>
                    <span className="farm-card-link">
                      Ver mi finca y sus cuentas →
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
          <p className="privacy-note">
            Tus fincas se guardan en este dispositivo. Puedes descargar una
            copia desde el detalle de cada finca.
          </p>
        </>
      )}
      {adding && (
        <Overlay
          title="Agregar una finca"
          onClose={() => setAdding(false)}
          className="farm-editor-overlay"
        >
          <div className="document-workspace">
            <FarmEditor initial={EMPTY_FARM} onCommit={create} />
          </div>
        </Overlay>
      )}
    </>
  );
}
