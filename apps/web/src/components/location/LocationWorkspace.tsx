"use client";
import { useEffect, useRef, useState } from "react";
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
import { EMPTY_PROFILE, hasPin } from "@/lib/farm-types";
import { inColombia, type LocationPoint } from "@/lib/location-types";
import { ZoneExplorer } from "./ZoneExplorer";
import { CleanSheet } from "./CleanSheet";
import { FarmWeather } from "./FarmWeather";
const STORAGE = "agroamigo-location-v1";
type SavedLocation = {
  point: LocationPoint | null;
  municipalityId: string;
  name: string;
  farmId?: string;
  method?: string;
  accuracy?: number | null;
  version?: number;
};
export function LocationWorkspace({ farmId }: { farmId?: string }) {
  const context = useFarm(),
    places = useData<Municipality[]>("/api/planning/municipalities");
  const [location, setLocation] = useState<SavedLocation>({
      point: null,
      municipalityId: "",
      name: "Mi finca",
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
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const save = (next: SavedLocation) => {
    let selectedId = next.farmId || farmId || context.activeFarm?.id || "";
    const existing = context.farms.find((f) => f.id === selectedId);
    if (next.point) {
      const profile = {
        ...(existing?.profile || EMPTY_PROFILE),
        name: next.name,
        latitude: next.point.latitude.toFixed(6),
        longitude: next.point.longitude.toFixed(6),
        locationMethod: next.method || "saved",
        locationAccuracy: next.accuracy == null ? "" : String(next.accuracy),
        // The municipality picker is a reference lookup. Keep an existing
        // farm's administrative identity and crop budgets when exploring.
        municipalityId: existing
          ? existing.profile.municipalityId
          : next.municipalityId,
      };
      if (existing) context.updateFarm(existing.id, profile);
      else selectedId = context.addFarm(profile);
    }
    const saved = { ...next, farmId: selectedId, version: 2 };
    setLocation(saved);
    try {
      localStorage.setItem(STORAGE, JSON.stringify(saved));
    } catch {
      setMessage(
        "La ubicación está en esta sesión, pero no pudimos guardarla en el dispositivo.",
      );
    }
  };
  useEffect(() => {
    if (!context.ready) return;
    const selected =
      context.farms.find((f) => f.id === farmId) || context.activeFarm;
    let saved: SavedLocation | null = null;
    try {
      const original = localStorage.getItem(STORAGE);
      const raw = JSON.parse(original || "null");
      if (
        raw &&
        typeof raw.municipalityId === "string" &&
        typeof raw.name === "string" &&
        (!raw.point || inColombia(raw.point))
      ) {
        if (!farmId && (!raw.farmId || raw.farmId === selected?.id))
          saved = raw;
        if (
          original &&
          raw.version !== 2 &&
          !localStorage.getItem("agroamigo-location-legacy-v1")
        )
          localStorage.setItem("agroamigo-location-legacy-v1", original);
      }
    } catch {
      setMessage(
        "No pudimos leer la ubicación guardada. La copia anterior se conserva.",
      );
    }
    if (selected && hasPin(selected.profile)) {
      saved = {
        point: {
          latitude: +selected.profile.latitude,
          longitude: +selected.profile.longitude,
        },
        municipalityId:
          saved?.farmId === selected.id
            ? saved.municipalityId
            : selected.profile.municipalityId,
        name: selected.profile.name,
        farmId: selected.id,
        method: selected.profile.locationMethod,
        accuracy: selected.profile.locationAccuracy
          ? +selected.profile.locationAccuracy
          : null,
        version: 2,
      };
    } else if (selected) {
      saved = {
        ...saved,
        point: saved?.point || null,
        municipalityId:
          saved?.farmId === selected.id
            ? saved.municipalityId
            : selected.profile.municipalityId || saved?.municipalityId || "",
        name: selected.profile.name,
        farmId: selected.id,
        version: 2,
      };
    }
    if (saved) {
      if (saved.point && (!selected || !hasPin(selected.profile)))
        save({ ...saved, farmId: selected?.id });
      else setLocation(saved);
      setFocus(saved.point);
    }
    setReady(true);
  }, [context.ready, farmId, context.activeFarm?.id]);
  const setPin = (
    point: LocationPoint,
    method = "pin",
    accuracy: number | null = null,
    name = location.name,
  ) => {
    if (!inColombia(point)) {
      setMessage("Selecciona un punto dentro del área de Colombia.");
      return;
    }
    setQuery("");
    save({ ...location, point, name, method, accuracy });
    setFocus({ ...point });
    setMessage(
      "Ubicación exacta guardada en tu finca. El municipio solo aporta referencias agrícolas; mover el mapa o cambiar esa referencia no mueve tu pin.",
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
        if (!live.current) return;
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
        setPin(point, "gps", p.coords.accuracy);
        setMessage(
          `Pin guardado con GPS (precisión aproximada ±${Math.round(p.coords.accuracy)} m). Confirma el municipio para ver sus referencias.`,
        );
      },
      (e) => {
        if (!live.current) return;
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
          <p>
            Ubica tu finca con un punto exacto para consultar el clima, el
            terreno y tus cuentas.
          </p>
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
                ? `${location.point.latitude.toFixed(6)}, ${location.point.longitude.toFixed(6)}`
                : "Aún no has marcado la ubicación de tu finca"}
            </span>
            {location.point && (
              <small>
                {location.method === "gps"
                  ? `GPS${location.accuracy == null ? "" : ` · precisión aproximada ±${Math.round(location.accuracy)} m`}`
                  : location.method === "manual"
                    ? "Coordenadas ingresadas por ti"
                    : location.method === "pin"
                      ? "Punto elegido en el mapa"
                      : "Ubicación exacta guardada"}
                . Este punto no representa el centro municipal ni define
                linderos.
              </small>
            )}
          </div>
        </div>
        <div className="location-actions">
          <button className="button secondary" onClick={() => {
            setTab("map");
            requestAnimationFrame(() => document.getElementById("zone-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }));
          }}><IoMapOutline /> Buscar en el mapa</button>
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
          {gps ? "Buscando…" : "Usar mi ubicación"}
          </button>
        </div>
        <p className="privacy-note">
          Usa el GPS cuando estés en la finca. También puedes buscar un municipio
          o un lugar en el mapa, acercarte y tocar el punto de tu finca.
        </p>
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
              setFocus({ latitude: p.latitude, longitude: p.longitude });
              setTab("map");
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
            Finca guardada
            <select
              value={location.farmId || ""}
              onChange={(e) => {
                const f = context.farms.find((f) => f.id === e.target.value);
                if (!f) return;
                const point = hasPin(f.profile)
                  ? {
                      latitude: +f.profile.latitude,
                      longitude: +f.profile.longitude,
                    }
                  : null;
                context.selectFarm(f.id);
                save({
                  point,
                  municipalityId: f.profile.municipalityId,
                  name: f.profile.name,
                  farmId: f.id,
                  method: f.profile.locationMethod,
                  accuracy: f.profile.locationAccuracy
                    ? +f.profile.locationAccuracy
                    : null,
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
      {context.storageError && (
        <p className="inline-note" role="alert">
          {context.storageError}
        </p>
      )}
      {message && (
        <p className="inline-note location-message" role="status">
          {message}
        </p>
      )}
      {location.point && <FarmWeather point={location.point} name={location.name} />}
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
        <ZoneExplorer pin={location.point} focus={focus} onPin={setPin} onExplore={setFocus} />
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
