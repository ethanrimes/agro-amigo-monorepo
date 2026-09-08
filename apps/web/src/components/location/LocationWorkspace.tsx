"use client";
import { useEffect, useState } from "react";
import {
  IoMapOutline,
  IoCalculatorOutline,
  IoLocateOutline,
  IoLocationOutline,
} from "react-icons/io5";
import { useFarm } from "@/components/planning/FarmContext";
import { useData } from "@/components/marketplace/useData";
import { SearchBox } from "@/components/ui/SearchBox";
import { ErrorState } from "@/components/marketplace/Shared";
import { CropOptions } from "@/components/planning/CropOptions";
import type { Municipality, FarmData } from "@/lib/planning-types";
import { hasPin } from "@/lib/farm-types";
import { inColombia, type LocationPoint } from "@/lib/location-types";
import { ZoneExplorer } from "./ZoneExplorer";
import { CleanSheet } from "./CleanSheet";
const STORAGE = "agroamigo-location-v1";
type SavedLocation = {
  point: LocationPoint | null;
  municipalityId: string;
  name: string;
};
export function LocationWorkspace({ farmId }: { farmId?: string }) {
  const context = useFarm(),
    places = useData<Municipality[]>("/api/planning/municipalities");
  const [location, setLocation] = useState<SavedLocation>({
      point: null,
      municipalityId: "",
      name: "Mi pin",
    }),
    [ready, setReady] = useState(false),
    [focus, setFocus] = useState<LocationPoint | null>(null),
    [tab, setTab] = useState("map"),
    [query, setQuery] = useState(""),
    [message, setMessage] = useState(""),
    [gps, setGps] = useState(false),
    [crops, setCrops] = useState(false),
    [financeVisited, setFinanceVisited] = useState(false),
    [selectedCrop, setSelectedCrop] = useState("");
  useEffect(() => {
    if (!context.ready) return;
    const legacy =
      context.farms.find((f) => f.id === farmId) || context.activeFarm;
    let saved: SavedLocation | null = null;
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE) || "null");
      if (
        !farmId &&
        raw &&
        typeof raw.municipalityId === "string" &&
        typeof raw.name === "string" &&
        (!raw.point || inColombia(raw.point))
      )
        saved = raw;
    } catch {
      setMessage(
        "No pudimos leer la ubicación guardada. La copia anterior se conserva.",
      );
    }
    if (!saved && legacy)
      saved = {
        point: hasPin(legacy.profile)
          ? {
              latitude: +legacy.profile.latitude,
              longitude: +legacy.profile.longitude,
            }
          : null,
        municipalityId: legacy.profile.municipalityId,
        name: legacy.profile.name,
      };
    if (saved) {
      setLocation(saved);
      setFocus(saved.point);
    }
    setReady(true);
  }, [context.ready, farmId]);
  const save = (next: SavedLocation) => {
    setLocation(next);
    try {
      localStorage.setItem(STORAGE, JSON.stringify(next));
    } catch {
      setMessage(
        "La ubicación está en esta sesión, pero no pudimos guardarla en el dispositivo.",
      );
    }
  };
  const setPin = (p: LocationPoint) => {
    setQuery("");
    save({ ...location, point: p, municipalityId: "" });
    setFocus({ ...p });
    setMessage(
      "Pin guardado. Confirma abajo el municipio para consultar sus referencias agrícolas. Mover el mapa no mueve tu pin.",
    );
  };
  const locate = () => {
    if (!navigator.geolocation) {
      setMessage(
        "Este dispositivo no ofrece GPS. Toca el mapa para fijar tu pin.",
      );
      return;
    }
    setGps(true);
    setMessage("Buscando la ubicación del dispositivo…");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setGps(false);
        const point = {
          latitude: p.coords.latitude,
          longitude: p.coords.longitude,
        };
        if (!inColombia(point)) {
          setMessage(
            "La ubicación recibida está fuera del área de consulta de Colombia. Puedes explorar el mapa y fijar un pin.",
          );
          return;
        }
        setPin(point);
        setMessage(
          `Pin guardado con GPS (precisión aproximada ±${Math.round(p.coords.accuracy)} m). Confirma el municipio para ver sus referencias.`,
        );
      },
      (e) => {
        setGps(false);
        setMessage(
          e.code === 1
            ? "El permiso de ubicación está desactivado. Puedes fijar el pin tocando el mapa."
            : "No pudimos obtener la ubicación. Intenta de nuevo al aire libre o usa el mapa.",
        );
      },
      { enableHighAccuracy: true, timeout: 18000, maximumAge: 0 },
    );
  };
  const data = useData<FarmData>(
      location.municipalityId
        ? "/api/planning/farm?id=" + location.municipalityId
        : null,
    ),
    municipality = places.data?.find((p) => p.id === location.municipalityId);
  if (!ready) return <p role="status">Cargando Mi finca…</p>;
  return (
    <div className="location-workspace">
      <header className="location-header">
        <div>
          <span className="eyebrow">MI FINCA</span>
          <h1>
            Conoce tu tierra.
            <br />
            Haz tus cuentas.
          </h1>
          <p>Clima, suelos y números para tomar mejores decisiones.</p>
        </div>
        <div className="location-header-icon">
          <IoMapOutline />
        </div>
      </header>
      <section className="location-toolbar panel">
        <div className="location-place">
          <IoLocationOutline />
          <div>
            <strong>
              {location.point ? location.name : "Explora Colombia"}
            </strong>
            <span>
              {location.point
                ? `${location.point.latitude.toFixed(5)}, ${location.point.longitude.toFixed(5)}`
                : "Busca un municipio o usa el mapa para comenzar"}
            </span>
          </div>
        </div>
        <div className="location-actions">
          {location.point && (
            <button
              className="button secondary"
              onClick={() => {
                setFocus({ ...location.point! });
                setTab("map");
              }}
            >
              Volver a mi pin
            </button>
          )}
          <button className="button primary" disabled={gps} onClick={locate}>
            <IoLocateOutline />
            {gps ? "Buscando…" : "Usar mi ubicación GPS"}
          </button>
        </div>
        <div className="location-search">
          <label>
            {location.point
              ? "Municipio para las referencias agrícolas"
              : "Explorar un municipio"}
          </label>
          <SearchBox
            label="Buscar municipio"
            placeholder="Municipio o departamento…"
            value={query}
            onChange={setQuery}
            options={(places.data || []).map((m) => ({
              id: m.id,
              label: m.name,
              detail: m.department,
            }))}
            onSelect={(o) => {
              const p = places.data!.find((p) => p.id === o.id)!;
              save({ ...location, municipalityId: p.id });
              if (!location.point)
                setFocus({ latitude: p.latitude, longitude: p.longitude });
              setMessage(
                "Referencias municipales: " +
                  p.name +
                  ", " +
                  p.department +
                  ". La selección no cambia tu pin.",
              );
            }}
          />
          {municipality && (
            <small>
              Municipio confirmado:{" "}
              <b>
                {municipality.name}, {municipality.department}
              </b>
              . Las referencias municipales no son mediciones del pin.
            </small>
          )}
          {places.error && (
            <ErrorState message={places.error} retry={places.retry} />
          )}
        </div>
        {context.farms.length > 0 && (
          <label className="legacy-locations">
            Consultar una ubicación anterior
            <select
              value=""
              onChange={(e) => {
                const f = context.farms.find((f) => f.id === e.target.value);
                if (!f) return;
                const point = hasPin(f.profile)
                  ? {
                      latitude: +f.profile.latitude,
                      longitude: +f.profile.longitude,
                    }
                  : null;
                save({
                  point,
                  municipalityId: f.profile.municipalityId,
                  name: f.profile.name,
                });
                setFocus(point);
                setMessage(
                  "Ubicación anterior cargada. Tus registros de cultivos y presupuestos previos siguen conservados en este dispositivo.",
                );
              }}
            >
              <option value="">Elige una ubicación guardada</option>
              {context.farms.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.profile.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </section>
      {message && (
        <p className="inline-note location-message" role="status">
          {message}
        </p>
      )}
      <div
        className="location-main-tabs"
        role="tablist"
        aria-label="Información de Mi finca"
      >
        <button
          id="zone-tab"
          role="tab"
          aria-selected={tab === "map"}
          aria-controls="zone-panel"
          onClick={() => setTab("map")}
        >
          <IoMapOutline />
          <span>
            Explorar mi zona<small>Clima, terreno y suelos</small>
          </span>
        </button>
        <button
          id="clean-tab"
          role="tab"
          aria-selected={tab === "finance"}
          aria-controls="clean-panel"
          onClick={() => {
            setFinanceVisited(true);
            setTab("finance");
          }}
        >
          <IoCalculatorOutline />
          <span>
            Costos y rentabilidad<small>Ingresos, costos y equilibrio</small>
          </span>
        </button>
      </div>
      <div
        id="zone-panel"
        role="tabpanel"
        aria-labelledby="zone-tab"
        hidden={tab !== "map"}
      >
        <ZoneExplorer pin={location.point} focus={focus} onPin={setPin} />
        {data.data && (
          <div className="location-crop-context">
            <button
              className="button secondary"
              aria-expanded={crops}
              onClick={() => setCrops(!crops)}
            >
              {crops
                ? "Cerrar cultivos de la zona"
                : "¿Qué se cultiva en este municipio?"}
            </button>
            {crops && (
              <CropOptions
                data={data.data}
                select={(c) => {
                  setSelectedCrop(c.crop_code);
                  setFinanceVisited(true);
                  setTab("finance");
                  setCrops(false);
                }}
              />
            )}
          </div>
        )}
      </div>
      {financeVisited && (
        <div
          hidden={tab !== "finance"}
          id="clean-panel"
          role="tabpanel"
          aria-labelledby="clean-tab"
        >
          {!location.municipalityId ? (
            <section className="panel clean-incomplete">
              <IoCalculatorOutline />
              <h2>Elige el municipio del análisis</h2>
              <p>
                Usa la búsqueda de arriba. Así podemos mostrar cultivos,
                rendimientos y estudios regionales con su fuente.
              </p>
            </section>
          ) : data.loading ? (
            <p role="status">Consultando referencias agrícolas…</p>
          ) : data.error ? (
            <ErrorState message={data.error} retry={data.retry} />
          ) : (
            data.data && (
              <CleanSheet
                key={location.municipalityId + "-" + selectedCrop}
                data={data.data}
                initialCrop={selectedCrop}
              />
            )
          )}
        </div>
      )}
      <p className="privacy-note">
        El pin se guarda en este dispositivo. Consultar capas envía sus
        coordenadas al servidor y a la fuente pública; conservamos la respuesta
        de datos en Azure para que puedas verificarla. Los supuestos económicos
        permanecen en esta sesión y puedes descargarlos con sus fuentes.
      </p>
    </div>
  );
}
