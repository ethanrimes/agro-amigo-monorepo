"use client";
import { useEffect, useRef, useState } from "react";
import type {
  Map as LibreMap,
  GeoJSONSource,
  MapMouseEvent,
} from "maplibre-gl";
import type { FeatureCollection, Geometry } from "geojson";
import { mapLibrary, mapSpanish } from "@/lib/maplibre";
import { Overlay } from "@/components/ui/Overlay";
import { SearchBox } from "@/components/ui/SearchBox";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { DetailTabs, type InformationMode } from "./DetailTabs";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { money, number, dateLabel, type Catalog } from "@/lib/market-types";
import type { InputPrice } from "@/lib/planning-types";
import type { MapData, MapPoint } from "@/lib/explore-types";
import { IoMapOutline } from "react-icons/io5";
import "maplibre-gl/dist/maplibre-gl.css";
const fold = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
type Kind = "product" | "market" | "input";
export function MapButton({
  kind,
  id,
  label = "Ver mapa",
}: {
  kind: Kind;
  id?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="button secondary map-button"
        onClick={(e) => {
          e.currentTarget.focus({ preventScroll: true });
          setOpen(true);
        }}
      >
        <IoMapOutline />
        {label}
      </button>
      {open && (
        <Overlay
          title={`${kind === "input" ? "Insumos" : kind === "market" ? "Mercados" : "Productos"} en Colombia`}
          className="map-overlay"
          onClose={() => setOpen(false)}
        >
          <MapView kind={kind} initialId={id} />
        </Overlay>
      )}
    </>
  );
}
function MapView({ kind, initialId }: { kind: Kind; initialId?: string }) {
  const catalog = useData<Catalog>(kind === "input" ? null : "/api/catalog");
  const inputs = useData<InputPrice[]>(
    kind === "input" ? "/api/planning/inputs" : null,
  );
  const [selected, setSelected] = useState(initialId || ""),
    [search, setSearch] = useState(""),
    [mode, setMode] = useState<InformationMode>("price");
  const [region, setRegion] = useState(""),
    [failure, setFailure] = useState(""),
    [ready, setReady] = useState(false);
  const host = useRef<HTMLDivElement>(null),
    map = useRef<LibreMap | null>(null),
    boundaries = useRef<FeatureCollection<Geometry> | null>(null);
  const options =
    kind === "input"
      ? Array.from(
          new Map(
            (inputs.data || []).map((i) => [
              i.id,
              { id: i.id, label: i.name + " · " + i.presentation },
            ]),
          ).values(),
        )
      : (catalog.data?.products || []).map((p) => ({
          id: p.id,
          label: p.name,
        }));
  useEffect(() => {
    if (!selected && kind !== "market" && options.length) {
      const o = options.find((o) => o.id === "aguacate-hass") || options[0];
      setSelected(o.id);
      setSearch(o.label);
    } else if (selected && !search)
      setSearch(options.find((o) => o.id === selected)?.label || "");
  }, [catalog.data, inputs.data, selected, kind]); // eslint-disable-line react-hooks/exhaustive-deps
  const data = useData<MapData>(
    "/api/explore/map?kind=" +
      kind +
      "&id=" +
      encodeURIComponent(selected) +
      "&mode=" +
      mode,
  );
  const current = useRef<MapData | null>(null);
  current.current = data.data;
  useEffect(() => {
    let live = true;
    (async () => {
      const [lib, response] = await Promise.all([
        mapLibrary(),
        fetch("/maps/colombia-departments.json"),
      ]);
      if (!response.ok) throw new Error("boundaries");
      const geo = await response.json();
      if (!live || !host.current) return;
      boundaries.current = geo;
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
                '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> · colaboradores',
            },
          },
          layers: [{ id: "base", type: "raster", source: "osm" }],
        },
        center: [-73, 4.4],
        zoom: 4,
        minZoom: 3,
        maxZoom: 12,
        attributionControl: { compact: true },
      });
      map.current = m;
      m.addControl(
        new lib.NavigationControl({ showCompass: false }),
        "top-right",
      );
      m.on("idle", () => {
        if (live && host.current && m.getLayer("department-fill"))
          host.current.dataset.features = String(
            m.queryRenderedFeatures({
              layers: ["department-fill", "market-dots", "clusters"],
            }).length,
          );
      });
      m.on("load", () => {
        if (!live) return;
        m.addSource("departments", { type: "geojson", data: geo });
        m.addLayer({
          id: "department-fill",
          type: "fill",
          source: "departments",
          paint: {
            "fill-color": [
              "case",
              ["has", "value"],
              [
                "interpolate",
                ["linear"],
                ["get", "value"],
                0,
                "#dceab2",
                1,
                "#146347",
              ],
              "#d9dfdf",
            ],
            "fill-opacity": 0.44,
          },
        });
        m.addLayer({
          id: "department-line",
          type: "line",
          source: "departments",
          paint: { "line-color": "#527467", "line-width": 1 },
        });
        m.addSource("markets", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
          cluster: true,
          clusterRadius: 24,
          clusterMaxZoom: 9,
        });
        m.addLayer({
          id: "clusters",
          type: "circle",
          source: "markets",
          filter: ["has", "point_count"],
          paint: {
            "circle-radius": 15,
            "circle-color": "#164d37",
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });
        m.addLayer({
          id: "market-dots",
          type: "circle",
          source: "markets",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-radius": 7,
            "circle-color": "#ad591e",
            "circle-stroke-width": 2,
            "circle-stroke-color": "#ffffff",
          },
        });
        m.on("click", (e: MapMouseEvent) => {
          const points = m.queryRenderedFeatures(e.point, {
            layers: ["market-dots", "clusters"],
          });
          if (points.length) {
            if (points[0].properties?.cluster) {
              const coordinates = (
                points[0].geometry as { coordinates: number[] }
              ).coordinates;
              m.flyTo({
                center: [coordinates[0], coordinates[1]],
                zoom: Math.min(12, m.getZoom() + 2),
              });
            }
            const d = points[0].properties?.region;
            if (d) setRegion(d);
            if (points[0].properties?.cluster) {
              const area = m.queryRenderedFeatures(e.point, {
                layers: ["department-fill"],
              })[0];
              if (area) setRegion(area.properties?.NOMBRE_DPT || "");
            }
            return;
          }
          const area = m.queryRenderedFeatures(e.point, {
            layers: ["department-fill"],
          })[0];
          if (area) setRegion(area.properties?.NOMBRE_DPT || "");
        });
        m.fitBounds(
          [
            [-81.8, -4.3],
            [-66.6, 13.6],
          ],
          { padding: 28, duration: 0 },
        );
        setReady(true);
      });
      m.on("error", () => {
        if (live && !m.isStyleLoaded())
          setFailure(
            "No se pudo cargar el mapa. Las referencias siguen disponibles en la lista.",
          );
      });
    })().catch(() => {
      if (live)
        setFailure(
          "Este dispositivo no pudo abrir el mapa. Puedes consultar las referencias en la lista.",
        );
    });
    return () => {
      live = false;
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !boundaries.current || !data.data) return;
    const groups = new Map<string, number[]>();
    for (const p of data.data.points) {
      groups.set(p.department_id, [
        ...(groups.get(p.department_id) || []),
        p.value,
      ]);
    }
    const values = new Map(
      [...groups].map(([k, v]) => [
        k,
        mode === "supply" || !selected
          ? v.reduce((a, b) => a + b, 0)
          : v.reduce((a, b) => a + b, 0) / v.length,
      ]),
    );
    const max = Math.max(1, ...values.values());
    const geo = {
      ...boundaries.current,
      features: boundaries.current.features.map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          ...(values.has(f.properties?.DPTO)
            ? { value: values.get(f.properties?.DPTO)! / max }
            : {}),
        },
      })),
    };
    (m.getSource("departments") as GeoJSONSource).setData(geo);
    (m.getSource("markets") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features:
        kind === "input"
          ? []
          : data.data.points.map((p) => ({
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: [p.longitude, p.latitude],
              },
              properties: { id: p.id, region: p.region },
            })),
    });
  }, [data.data, ready, mode, selected, kind]);
  const matches =
    data.data?.points.filter(
      (p) =>
        !region ||
        fold(p.region) === fold(region) ||
        (p.department_id === "11" && region === "SANTAFE DE BOGOTA D.C"),
    ) || [];
  const regions = Array.from(
    new Set(data.data?.points.map((p) => p.region) || []),
  ).sort();
  const display = (p: MapPoint) =>
    p.unit.startsWith("COP") ? money(p.value) : number(p.value);
  return (
    <div className="map-workspace">
      <div className="map-controls">
        <SearchBox
          label={
            kind === "input"
              ? "Elegir insumo en el mapa"
              : "Elegir producto en el mapa"
          }
          placeholder={
            kind === "market" ? "Todos los productos" : "Buscar para comparar"
          }
          value={search}
          onChange={(v) => {
            setSearch(v);
            if (!v && kind === "market") setSelected("");
          }}
          options={options}
          onSelect={(o) => {
            setSelected(o.id);
            setRegion("");
          }}
        />
        {kind !== "input" && <DetailTabs mode={mode} onChange={setMode} />}
      </div>
      <div className="map-layout">
        <div className="map-stage">
          <div
            className="colombia-map"
            ref={host}
            role="img"
            aria-label="Mapa interactivo de Colombia por departamentos"
            data-ready={ready}
          />
          <button
            className="button secondary map-reset"
            onClick={() => {
              map.current?.fitBounds(
                [
                  [-81.8, -4.3],
                  [-66.6, 13.6],
                ],
                { padding: 28 },
              );
              setRegion("");
            }}
          >
            Toda Colombia
          </button>
          <div className="map-legend">
            <span className="map-scale" />
            Menor · Mayor
            <span className="map-no-data" />
            Sin dato
          </div>
          {failure && (
            <p className="map-failure" role="alert">
              {failure}
            </p>
          )}
        </div>
        <aside className="map-results">
          <label className="form-field">
            Departamento
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">Toda Colombia</option>
              {region && !regions.includes(region) && <option>{region}</option>}
              {regions.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <h3>{matches.length} referencias</h3>
          <p className="field-help">{data.data?.basis}</p>
          {data.loading ? (
            <p role="status">Consultando el mapa…</p>
          ) : data.error ? (
            <ErrorState message={data.error} retry={data.retry} />
          ) : (
            <div className="map-reference-list">
              {matches.slice(0, 80).map((p) => (
                <article key={p.id}>
                  <strong>{p.name}</strong>
                  <span>
                    {display(p)} <small>{p.unit}</small>
                  </span>
                  <small>{p.date && dateLabel(p.date, true)}</small>
                  {kind !== "input" ? (
                    <a href={"/market/" + p.id}>Abrir mercado →</a>
                  ) : (
                    <EvidenceLink
                      id={p.document_id}
                      input={selected}
                      department={p.region}
                    >
                      Ver fuente
                    </EvidenceLink>
                  )}
                </article>
              ))}
              {!matches.length && (
                <p>
                  No hay datos publicados para esta selección. Prueba otro
                  producto o departamento.
                </p>
              )}
            </div>
          )}
          {kind !== "input" && (
            <p className="privacy-note">
              Los puntos indican el municipio, no la dirección exacta de cada
              mercado.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
