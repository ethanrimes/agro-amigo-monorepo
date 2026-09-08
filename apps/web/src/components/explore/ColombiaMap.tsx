"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AppliedFilters, priceSeriesLabel } from "./AppliedFilters";
import type {
  Map as LibreMap,
  GeoJSONSource,
  MapMouseEvent,
  Popup,
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
import type { CatalogCard } from "@/lib/catalog-display";
import type { InputPrice } from "@/lib/planning-types";
import type { MapData, MapPoint, MapFilters } from "@/lib/explore-types";
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
  filters = {},
}: {
  kind: Kind;
  id?: string;
  label?: string;
  filters?: MapFilters;
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
          <MapView kind={kind} initialId={id} initialFilters={filters} />
        </Overlay>
      )}
    </>
  );
}
function MapView({
  kind,
  initialId,
  initialFilters,
}: {
  kind: Kind;
  initialId?: string;
  initialFilters: MapFilters;
}) {
  const [requested, setRequested] = useState(initialFilters);
  const [popup, setPopup] = useState<{
    node: HTMLElement;
    points: MapPoint[];
    title: string;
  } | null>(null);
  const bubble = useRef<Popup | null>(null);
  const showPopup = useRef<
    (points: MapPoint[], title: string, coords: [number, number]) => void
  >(() => {});
  const catalog = useData<Catalog>(kind === "input" ? null : "/api/catalog");
  const inputs = useData<InputPrice[]>(
    kind === "input"
      ? "/api/planning/inputs?" +
          new URLSearchParams({
            grouped: "true",
            scope: requested.scope || "department",
            department: requested.region || "",
            history: "recent",
          })
      : null,
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
            (inputs.data || [])
              .filter(
                (i) =>
                  (!requested.category || i.category === requested.category) &&
                  (!requested.query ||
                    fold(
                      i.name +
                        " " +
                        i.presentation +
                        " " +
                        i.brand +
                        " " +
                        i.registration +
                        " " +
                        i.category,
                    ).includes(fold(requested.query))),
              )
              .map((i) => [
                i.id,
                { id: i.id, label: i.name + " · " + i.presentation },
              ]),
          ).values(),
        )
      : (catalog.data?.products || []).filter((p: CatalogCard) => p.map_supported !== false).map((p) => ({
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
    "/api/explore/map?" +
      new URLSearchParams({ kind, id: selected, mode, ...requested }),
  );
  const filters = data.data?.filters || requested;
  function changeFilter(name: keyof MapFilters, value: string) {
    setRequested((current) => ({
      ...current,
      [name]: value,
      ...(name === "series"
        ? { presentation: "", units: "" }
        : name === "presentation"
          ? { units: "" }
          : {}),
    }));
    bubble.current?.remove();
    setPopup(null);
  }
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
      showPopup.current = (points, title, coords) => {
        bubble.current?.remove();
        const node = document.createElement("div");
        node.className = "map-price-popup";
        const next = new lib.Popup({
          anchor: "bottom",
          maxWidth: "340px",
          closeOnClick: false,
          offset: 12,
        })
          .setLngLat(coords)
          .setDOMContent(node)
          .addTo(m);
        bubble.current = next;
        setPopup({ node, points, title });
        next.on("close", () =>
          setPopup((old) => (old?.node === node ? null : old)),
        );
      };
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
            if (!points[0].properties?.cluster) {
              const hit = current.current?.points.find(
                (p) => p.id === points[0].properties?.id,
              );
              if (hit) {
                const coincident = current.current!.points.filter(
                  (p) =>
                    p.latitude === hit.latitude &&
                    p.longitude === hit.longitude,
                );
                showPopup.current(coincident, hit.region, [
                  hit.longitude,
                  hit.latitude,
                ]);
              }
            }
            return;
          }
          const area = m.queryRenderedFeatures(e.point, {
            layers: ["department-fill"],
          })[0];
          if (area) {
            const name = area.properties?.NOMBRE_DPT || "";
            const found =
              current.current?.points.filter(
                (p) =>
                  fold(p.region) === fold(name) ||
                  (p.department_id === "11" &&
                    name === "SANTAFE DE BOGOTA D.C"),
              ) || [];
            showPopup.current(found, name, [e.lngLat.lng, e.lngLat.lat]);
          }
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
            "No se pudo cargar el mapa. Puedes abrir los precios con el selector de departamento.",
          );
      });
    })().catch(() => {
      if (live)
        setFailure(
          "Este dispositivo no pudo abrir el mapa. Cierra esta ventana para consultar los precios.",
        );
    });
    return () => {
      live = false;
      bubble.current?.remove();
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    if (!popup || !bubble.current || !map.current) return;
    const frame = requestAnimationFrame(() => {
      const m = map.current,
        panel = bubble.current;
      if (!m || !panel || !popup.node.isConnected) return;
      m.resize();
      const height =
        popup.node.parentElement?.getBoundingClientRect().height ||
        popup.node.offsetHeight;
      const mapHeight = m.getContainer().clientHeight;
      m.easeTo({
        center: panel.getLngLat(),
        zoom: Math.max(6, m.getZoom()),
        offset: [0, Math.min(mapHeight / 2 - 30, (height + 24) / 2)],
        duration: 250,
      });
      panel.setLngLat(panel.getLngLat());
    });
    return () => cancelAnimationFrame(frame);
  }, [popup]);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !boundaries.current || !data.data) return;
    bubble.current?.remove();
    setPopup(null);
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
        kind === "input" && requested.scope !== "municipality"
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
            bubble.current?.remove();
            setPopup(null);
            setSelected(o.id);
            setRegion("");
            setRequested(kind === "input" ? requested : {});
          }}
        />
        {kind !== "input" && <DetailTabs mode={mode} onChange={setMode} />}
      </div>
      {mode === "price" && data.data?.options && (
        <div className="map-price-filters">
          <label className="form-field">
            Tipo de precio
            <select
              aria-label="Tipo de precio en mapa"
              value={filters.series}
              onChange={(e) => changeFilter("series", e.target.value)}
            >
              {data.data.options.series.map((s) => (
                <option key={s} value={s}>
                  {priceSeriesLabel[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Presentación
            <select
              aria-label="Presentación en mapa"
              value={filters.presentation}
              onChange={(e) => changeFilter("presentation", e.target.value)}
            >
              {data.data.options.presentations.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="form-field">
            Unidades
            <select
              aria-label="Unidades en mapa"
              value={filters.units}
              onChange={(e) => changeFilter("units", e.target.value)}
            >
              {data.data.options.units.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      <AppliedFilters
        items={[
          {
            label: "Producto",
            value:
              data.data?.selection_label ||
              options.find((o) => o.id === selected)?.label ||
              search ||
              (selected ? "Referencia seleccionada" : "Todos"),
          },
          {
            label: "Datos",
            value:
              mode === "supply"
                ? "Abastecimiento"
                : priceSeriesLabel[filters.series || ""] || "Precios",
          },
          {
            label: "Presentación",
            value: mode === "price" ? filters.presentation || "" : "",
          },
          {
            label: "Unidades",
            value: mode === "price" ? filters.units || "" : "",
          },
          {
            label: "Mercado",
            value:
              kind === "input"
                ? ""
                : mode === "price"
                  ? data.data?.options?.markets.find(
                      (m) => m.id === filters.market,
                    )?.name || "Todos"
                  : "Todos",
          },
          { label: "Departamento", value: filters.region || "Colombia" },
          { label: "Categoría", value: filters.category || "" },
          { label: "Búsqueda", value: filters.query || "" },
          {
            label: "Municipio",
            value: kind === "input" ? filters.municipality || "" : "",
          },
          {
            label: "Cobertura",
            value:
              kind === "input"
                ? filters.scope === "municipality"
                  ? "Municipio"
                  : "Promedio departamental"
                : "",
          },
        ]}
      />
      <div className="map-summary">
        <label className="form-field">
          Abrir precios de un departamento
          <select
            value={region}
            onChange={(e) => {
              const value = e.target.value;
              setRegion(value);
              const found =
                data.data?.points.filter((p) => !value || p.region === value) ||
                [];
              if (found.length) {
                const first = found[0];
                showPopup.current(found, value || "Colombia", [
                  first.longitude,
                  first.latitude,
                ]);
              }
            }}
          >
            <option value="">Toca un punto o departamento</option>
            {regions.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <p>{data.data?.basis}</p>
      </div>
      {data.loading ? (
        <p role="status">Consultando el mapa…</p>
      ) : data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : !data.data?.points.length ? (
        <p className="empty-state">
          No hay precios con ubicación para estos filtros.
        </p>
      ) : (
        <p className="map-hint">
          {data.data.points.length} referencias · Toca un punto o departamento
          para abrir sus precios.
        </p>
      )}
      <div className="map-layout map-popup-layout">
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
              bubble.current?.remove();
              setPopup(null);
            }}
          >
            Toda Colombia
          </button>
          <div className="map-legend" hidden={Boolean(popup)}>
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
      </div>
      {popup &&
        createPortal(
          <>
            <h3>{popup.title}</h3>
            <div className="map-popup-quotes">
              {popup.points.length ? (
                popup.points
                  .slice()
                  .sort((a, b) => b.value - a.value)
                  .map((p) => (
                    <article key={p.id}>
                      <strong>{p.name}</strong>
                      <span className="map-popup-price">{display(p)}</span>
                      <small>{p.unit}</small>
                      <small>{p.date && dateLabel(p.date, true)}</small>
                      {kind !== "input" && (
                        <a href={"/market/" + p.id}>Abrir mercado →</a>
                      )}
                      <EvidenceLink
                        id={p.document_id}
                        page={p.source_page}
                        locator={p.source_locator}
                        input={kind === "input" ? selected : undefined}
                        department={kind === "input" ? p.region : undefined}
                      >
                        Consultar fuente
                      </EvidenceLink>
                    </article>
                  ))
              ) : (
                <p>No hay precios publicados para esta selección.</p>
              )}
            </div>
          </>,
          popup.node,
        )}
    </div>
  );
}
