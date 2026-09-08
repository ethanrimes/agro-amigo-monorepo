"use client";
import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, Marker, GeoJSONSource } from "maplibre-gl";
import { mapLibrary, mapSpanish } from "@/lib/maplibre";
import type {
  LocationPoint,
  SpatialLayer,
  ForecastGrid,
  LayerKey,
} from "@/lib/location-types";
import { forecastValue } from "@/lib/location-types";
import "maplibre-gl/dist/maplibre-gl.css";
export function LocationMap({
  pin,
  focus,
  inspection,
  layer,
  month,
  forecast,
  category,
  day,
  opacity,
  onInspect,
  onViewport,
}: {
  pin: LocationPoint | null;
  focus: LocationPoint | null;
  inspection: LocationPoint | null;
  layer: SpatialLayer | null;
  month: number;
  forecast: ForecastGrid | null;
  category: LayerKey;
  day: number | null;
  opacity: number;
  onInspect: (p: LocationPoint) => void;
  onViewport: (p: LocationPoint, step: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<LibreMap | null>(null),
    pinMarker = useRef<Marker | null>(null),
    inspectMarker = useRef<Marker | null>(null),
    callbacks = useRef({ onInspect, onViewport });
  callbacks.current = { onInspect, onViewport };
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [tiles, setTiles] = useState(0);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    let observer: ResizeObserver;
    void mapLibrary()
      .then((lib) => {
        if (!live || !host.current) return;
        const p = pin || focus;
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
            layers: [
              {
                id: "base",
                source: "osm",
                type: "raster",
                paint: { "raster-saturation": -0.65 },
              },
            ],
          },
          center: p ? [p.longitude, p.latitude] : [-74, 4.5],
          zoom: p ? 8 : 4.5,
          minZoom: 3,
          maxZoom: 17,
          attributionControl: { compact: true },
        });
        map.current = m;
        observer = new ResizeObserver(() => m.resize());
        observer.observe(host.current);
        m.addControl(new lib.NavigationControl({ showCompass: false }));
        m.addControl(new lib.ScaleControl({ unit: "metric" }), "bottom-left");
        const viewport = () => {
          clearTimeout(timer);
          timer = setTimeout(() => {
            if (!live) return;
            const p = m.getCenter(),
              b = m.getBounds(),
              width = Math.max(
                b.getEast() - b.getWest(),
                b.getNorth() - b.getSouth(),
              );
            const step = [0.25, 0.5, 1, 2, 4].find((s) => s * 4 >= width) || 4;
            callbacks.current.onViewport(
              { latitude: p.lat, longitude: p.lng },
              step,
            );
          }, 600);
        };
        m.on("load", () => {
          if (live) {
            setReady(true);
            viewport();
          }
        });
        m.on("moveend", viewport);
        m.on("click", (e) =>
          callbacks.current.onInspect({
            latitude: e.lngLat.lat,
            longitude: e.lngLat.lng,
          }),
        );
        m.on("sourcedata", (e) => {
          if (e.sourceId === "topic" && e.isSourceLoaded && live) {
            setTiles((n) => n + 1);
            setError("");
          }
        });
        m.on("error", (e) => {
          if (live && "sourceId" in e && e.sourceId === "topic")
            setError(
              "La capa no terminó de cargar. Puedes reintentar cambiando la capa; los valores del punto se consultan por separado.",
            );
        });
      })
      .catch(() => {
        if (live) setError("No pudimos abrir el mapa en este dispositivo.");
      });
    return () => {
      live = false;
      observer?.disconnect();
      clearTimeout(timer);
      pinMarker.current?.remove();
      inspectMarker.current?.remove();
      map.current?.remove();
      map.current = null;
      pinMarker.current = null;
      inspectMarker.current = null;
    };
  }, []);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    let live = true;
    void mapLibrary().then((lib) => {
      if (!live) return;
      for (const [point, marker, color, label] of [
        [pin, pinMarker, "#bc551c", "Pin de mi finca"],
        [inspection, inspectMarker, "#263e80", "Punto explorado"],
      ] as const) {
        if (point) {
          if (!marker.current) {
            marker.current = new lib.Marker({
              color,
              scale: point === pin ? 1.1 : 0.85,
            })
              .setLngLat([point.longitude, point.latitude])
              .addTo(m);
            marker.current.getElement().setAttribute("aria-label", label);
          } else marker.current.setLngLat([point.longitude, point.latitude]);
        } else {
          marker.current?.remove();
          marker.current = null;
        }
      }
    });
    return () => {
      live = false;
    };
  }, [
    ready,
    pin?.latitude,
    pin?.longitude,
    inspection?.latitude,
    inspection?.longitude,
  ]);
  useEffect(() => {
    if (ready && focus)
      map.current?.flyTo({
        center: [focus.longitude, focus.latitude],
        zoom: 8,
        duration: 350,
      });
  }, [ready, focus]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    setTiles(0);
    setError("");
    if (m.getLayer("topic-fill")) m.removeLayer("topic-fill");
    if (m.getSource("topic")) m.removeSource("topic");
    if (layer) {
      m.addSource("topic", {
        type: "raster",
        tileSize: 256,
        tiles: [
          `${window.location.origin}/api/location/tile?layer=${layer.id}&month=${month}&bbox={bbox-epsg-3857}`,
        ],
        attribution: `${layer.publisher} · ${layer.period}`,
      });
      m.addLayer({
        id: "topic-fill",
        source: "topic",
        type: "raster",
        paint: { "raster-opacity": opacity, "raster-fade-duration": 150 },
      });
    }
  }, [ready, layer?.id, month]);
  useEffect(() => {
    if (ready && map.current?.getLayer("topic-fill"))
      map.current.setPaintProperty("topic-fill", "raster-opacity", opacity);
  }, [ready, opacity]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const m = map.current;
    const features = layer
      ? []
      : (forecast?.samples || []).map((p) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [p.longitude, p.latitude],
          },
          properties: { value: forecastValue(p, category, day) },
        }));
    const data = { type: "FeatureCollection" as const, features };
    if (m.getSource("forecast"))
      (m.getSource("forecast") as GeoJSONSource).setData(data);
    else m.addSource("forecast", { type: "geojson", data });
    if (m.getLayer("forecast-points")) m.removeLayer("forecast-points");
    const colors =
      category === "rain"
        ? [
            "step",
            ["get", "value"],
            "#e1e8bc",
            10,
            "#a5d5dc",
            30,
            "#4f9bb9",
            80,
            "#176696",
            150,
            "#40337d",
          ]
        : category === "temperature"
          ? [
              "step",
              ["get", "value"],
              "#5798ba",
              15,
              "#8fbdb5",
              24,
              "#e4c761",
              30,
              "#dc824e",
              35,
              "#a53d3d",
            ]
          : ["case", ["==", ["get", "value"], 1], "#da912c", "#6b8d86"];
    m.addLayer({
      id: "forecast-points",
      source: "forecast",
      type: "circle",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 6, 9, 16],
        "circle-color": [
          "case",
          ["==", ["get", "value"], null],
          "#b6b7b8",
          colors,
        ] as never,
        "circle-opacity": opacity,
        "circle-stroke-width": 2,
        "circle-stroke-color": "#fff",
      },
    });
  }, [ready, forecast, layer?.id, category, day, opacity]);
  return (
    <div className="zone-map-frame">
      <div
        ref={host}
        className="zone-map"
        role="region"
        aria-label="Mapa de capas de mi finca"
        data-ready={ready}
        data-layer={layer?.id || category + "-forecast"}
        data-tiles={tiles}
        data-points={layer ? 0 : forecast?.samples.length || 0}
        data-pin-lat={pin?.latitude}
        data-pin-lon={pin?.longitude}
      />
      {!ready && !error && (
        <p className="zone-map-status" role="status">
          Abriendo el mapa de Colombia…
        </p>
      )}
      {error && (
        <p className="zone-map-status warning" role="alert">
          {error}
        </p>
      )}
      <span className="zone-map-hint">
        Toca cualquier lugar para consultar sus datos
      </span>
    </div>
  );
}
