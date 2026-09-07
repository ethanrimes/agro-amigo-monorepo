"use client";
import { useRef, useEffect, useState } from "react";
import { IoLocateOutline } from "react-icons/io5";
import { FarmMap } from "./FarmMap";
import type { FarmProfile, Municipality } from "@/lib/planning-types";
import { hasPin } from "@/lib/farm-types";
export function FarmLocation({
  draft,
  places,
  onChange,
}: {
  draft: FarmProfile;
  places: Municipality[];
  onChange: (p: Partial<FarmProfile>) => void;
}) {
  const selected = places.find((m) => m.id === draft.municipalityId),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const choose = (
    latitude: number,
    longitude: number,
    method: string,
    accuracy = "",
  ) => {
    if (latitude < -5 || latitude > 14 || longitude < -82 || longitude > -66) {
      setMessage(
        "Este punto está fuera del área de consulta. Acerca el mapa a tu finca en Colombia.",
      );
      return;
    }
    onChange({
      latitude: latitude.toFixed(6),
      longitude: longitude.toFixed(6),
      locationMethod: method,
      locationAccuracy: accuracy,
    });
    setMessage(
      method === "gps"
        ? `Ubicación recibida${accuracy ? " · precisión aproximada de " + Math.round(+accuracy) + " m" : ""}. Revisa el pin y confirma el municipio.`
        : "Pin seleccionado. Confirma que el municipio corresponda a tu finca.",
    );
  };
  const locate = () => {
    if (!navigator.geolocation) {
      setMessage(
        "Este dispositivo no ofrece GPS. Pon el pin en el mapa o ingresa las coordenadas.",
      );
      return;
    }
    setBusy(true);
    setMessage("Buscando tu ubicación…");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        if (!live.current) return;
        setBusy(false);
        choose(
          p.coords.latitude,
          p.coords.longitude,
          "gps",
          String(p.coords.accuracy),
        );
      },
      (e) => {
        if (!live.current) return;
        setBusy(false);
        setMessage(
          e.code === 1
            ? "El permiso de ubicación está desactivado. Puedes activarlo en los ajustes o poner el pin en el mapa."
            : "No pudimos obtener tu ubicación. Vuelve a intentar al aire libre o pon el pin en el mapa.",
        );
      },
      { enableHighAccuracy: true, timeout: 18000, maximumAge: 0 },
    );
  };
  return (
    <section className="farm-location-editor">
      <div className="section-heading">
        <div>
          <h3>Ubica tu finca</h3>
          <p>Pon un pin o usa el GPS si estás en la finca.</p>
        </div>
        <button
          className="button secondary"
          type="button"
          disabled={busy}
          onClick={locate}
        >
          <IoLocateOutline />
          {busy ? "Buscando ubicación…" : "Usar mi ubicación GPS"}
        </button>
      </div>
      <FarmMap
        name={draft.name}
        point={
          hasPin(draft)
            ? { latitude: +draft.latitude, longitude: +draft.longitude }
            : null
        }
        center={selected}
        editable
        onPick={(p) => choose(p.latitude, p.longitude, "pin")}
      />
      {message && (
        <p className="inline-note" role="status">
          {message}
        </p>
      )}
      {hasPin(draft) && (
        <p className="location-coordinate">
          Pin: {(+draft.latitude).toFixed(5)}, {(+draft.longitude).toFixed(5)}
          {draft.locationMethod === "gps" && draft.locationAccuracy
            ? " · GPS ± " + Math.round(+draft.locationAccuracy) + " m"
            : ""}
        </p>
      )}
      <p className="privacy-note">
        La ubicación se guarda en este dispositivo. El pronóstico usa
        coordenadas redondeadas; el mapa no define linderos.
      </p>
    </section>
  );
}
