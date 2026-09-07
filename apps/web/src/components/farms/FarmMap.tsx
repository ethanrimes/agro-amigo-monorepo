"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, Marker } from "maplibre-gl";
import { mapLibrary, mapSpanish } from "@/lib/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
type Point = { latitude: number; longitude: number };
export function FarmMap({
  point,
  center,
  editable = false,
  onPick,
  name = "Tu finca",
}: {
  point: Point | null;
  center?: Point;
  editable?: boolean;
  onPick?: (p: Point) => void;
  name?: string;
}) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<LibreMap | null>(null),
    marker = useRef<Marker | null>(null),
    pick = useRef(onPick);
  const [ready, setReady] = useState(false),
    [error, setError] = useState("");
  pick.current = onPick;
  useEffect(() => {
    let live = true;
    void mapLibrary()
      .then((lib) => {
        if (!live || !host.current) return;
        const target = point || center;
        const m = new lib.Map({
          container: host.current,
          locale: mapSpanish,
          style: {
            version: 8,
            sources: {
              osm: {
                type: "raster",
                tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                tileSize: 256,
                attribution:
                  '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
              },
            },
            layers: [{ id: "base", type: "raster", source: "osm" }],
          },
          center: target ? [target.longitude, target.latitude] : [-74, 4.5],
          zoom: point ? 14 : center ? 10 : 4,
          minZoom: 3,
          maxZoom: 18,
          attributionControl: { compact: true },
        });
        map.current = m;
        m.addControl(new lib.NavigationControl({ showCompass: false }));
        m.on("load", () => {
          if (live) setReady(true);
        });
        if (editable) {
          m.getCanvas().style.cursor = "crosshair";
          m.on("click", (e) =>
            pick.current?.({ latitude: e.lngLat.lat, longitude: e.lngLat.lng }),
          );
        }
      })
      .catch(() => {
        if (live)
          setError(
            "No pudimos abrir el mapa. Puedes usar el GPS o ingresar las coordenadas.",
          );
      });
    return () => {
      live = false;
      marker.current?.remove();
      marker.current = null;
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    let live = true;
    void mapLibrary().then((lib) => {
      if (!live) return;
      if (point) {
        if (!marker.current) {
          marker.current = new lib.Marker({
            color: "#ad591e",
            draggable: editable,
          })
            .setLngLat([point.longitude, point.latitude])
            .addTo(m);
          marker.current
            .getElement()
            .setAttribute("aria-label", "Ubicación guardada de " + name);
          marker.current.on("dragend", () => {
            const p = marker.current!.getLngLat();
            pick.current?.({ latitude: p.lat, longitude: p.lng });
          });
        } else marker.current.setLngLat([point.longitude, point.latitude]);
        m.flyTo({
          center: [point.longitude, point.latitude],
          zoom: Math.max(14, m.getZoom()),
          duration: 0,
        });
      } else {
        marker.current?.remove();
        marker.current = null;
        if (center)
          m.flyTo({
            center: [center.longitude, center.latitude],
            zoom: 10,
            duration: 0,
          });
      }
    });
    return () => {
      live = false;
    };
  }, [
    ready,
    point?.latitude,
    point?.longitude,
    center?.latitude,
    center?.longitude,
    editable,
    name,
  ]);
  return (
    <div className="farm-map-wrap">
      <div
        ref={host}
        className="farm-location-map"
        role="img"
        aria-label={
          point ? "Mapa con el pin de " + name : "Mapa para ubicar la finca"
        }
        data-ready={ready}
        data-latitude={point?.latitude}
        data-longitude={point?.longitude}
      />
      {!ready && !error && (
        <p className="farm-map-loading" role="status">
          Abriendo mapa…
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {editable && (
        <p className="field-help">
          Toca el mapa para poner el pin. Puedes arrastrarlo y acercar el mapa
          para ajustar la ubicación.
        </p>
      )}
    </div>
  );
}
