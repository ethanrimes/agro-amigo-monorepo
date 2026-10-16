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
import { departmentOutlines } from "@/lib/map-boundaries";
import { mapLibrary, mapSpanish } from "@/lib/maplibre";
import { Overlay } from "@/components/ui/Overlay";
import { SearchBox } from "@/components/ui/SearchBox";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import { HierarchicalCategorySelect } from "@/components/ui/HierarchicalCategorySelect";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { DetailTabs, type InformationMode } from "./DetailTabs";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import { SupplyMapEvidence } from "./SupplyMapEvidence";
import { money, number, dateLabel, type Catalog } from "@/lib/market-types";
import type { CatalogCard } from "@/lib/catalog-display";
import { departmentKey, departmentLabel, departmentLabels } from "@/lib/filter-labels";
import type { InputPrice } from "@/lib/planning-types";
import { fold } from "@/lib/planning-math";
import { normalizeLabel } from "@/lib/label-normalization";
import { wagePaymentBasis, wagePresentationDisplay, wageRateUnitDisplay } from "@/lib/wage-basis-display";
import { quotePresentationOptions } from "@/lib/quote-filter-options";
import { categoryMatches, productCategoryPaths } from "@/lib/category-hierarchy";
import type { MapData, MapPoint, MapFilters } from "@/lib/explore-types";
import { resolveInputIdentity } from "@/lib/input-identity-equivalence";
import { IoMapOutline } from "react-icons/io5";
import "maplibre-gl/dist/maplibre-gl.css";
type Kind = "product" | "market" | "input";
export function MapButton({
  kind,
  id,
  label = "Ver mapa",
  filters = {},
  disabled = false,
}: {
  kind: Kind;
  id?: string;
  label?: string;
  filters?: MapFilters;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="button secondary map-button"
        disabled={disabled}
        onClick={(e) => {
          e.currentTarget.focus({ preventScroll: true });
          setOpen(true);
        }}
      >
        <IoMapOutline />
        {label}
      </button>
      {open && !disabled && (
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
  const [popupQuote, setPopupQuote] = useState("");
  const bubble = useRef<Popup | null>(null);
  const showPopup = useRef<
    (points: MapPoint[], title: string, coords: [number, number]) => void
  >(() => {});
  const catalog = useData<Catalog>(
    kind === "input"
      ? null
      : "/api/catalog?" + new URLSearchParams({ view: "canonical", region: requested.region || "" }),
  );
  const inputs = useData<InputPrice[]>(
    kind === "input"
      ? "/api/planning/inputs?" +
          new URLSearchParams({
            grouped: "true",
            scope: requested.scope || "department",
            department: requested.region || "",
            history: requested.history === "all" ? "all" : "recent",
          })
      : null,
  );
  const [selected, setSelected] = useState(initialId || ""),
    [search, setSearch] = useState(""),
    [mode, setMode] = useState<InformationMode>("price");
  const searchFocused = useRef(false);
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
                  categoryMatches(i.category, requested.category || "") &&
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
                { id: i.id, label: i.name + " · " + wagePresentationDisplay(i.name, i.presentation),
                  searchText: i.name + " " + i.presentation },
              ]),
          ).values(),
        )
      : (catalog.data?.products || []).filter((p: CatalogCard) =>
          p.map_supported !== false && productCategoryPaths(p).some((path) => categoryMatches(path, requested.category || ""))).map((p) => ({
          id: p.id,
          label: p.name,
        }));
  const categoryPaths = kind === "input"
    ? (inputs.data || []).map((item) => item.category)
    : (catalog.data?.products || []).flatMap(productCategoryPaths);
  useEffect(() => {
    if (kind === "input" && selected) {
      const canonical = resolveInputIdentity(selected).canonicalId;
      if (canonical !== selected) {
        setSelected(canonical);
        return;
      }
    }
    if (!selected && !search && !searchFocused.current && kind !== "market" && options.length) {
      const o = options.find((o) => o.id === "aguacate-hass") || options[0];
      setSelected(o.id);
      setSearch(current => current || o.label);
    } else if (selected && !search && !searchFocused.current)
      setSearch(current => current || options.find((o) => o.id === selected)?.label || "");
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
      const { data: geo, rejectedPolygons } = departmentOutlines(await response.json());
      if (!live || !host.current) return;
      host.current.dataset.outlineFeatures = String(geo.features.length);
      host.current.dataset.outlineRejected = String(rejectedPolygons);
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
        setPopupQuote("");
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
      const mapHeight = m.getContainer().clientHeight;
      // One scroll area keeps both the chooser and quote links reachable even
      // when a long selected label uses most of a phone's available map height.
      popup.node.style.maxHeight = `${Math.max(180, mapHeight - 60)}px`;
      const chosen = popup.node.querySelector<HTMLElement>('[data-selected-quote="true"]');
      // WebKit keeps a focused search input visible after its value changes,
      // which can undo the popup scroll. Move focus to the explicitly chosen
      // result, also dismissing the phone keyboard before exposing its source.
      chosen?.focus({ preventScroll: true });
      if (chosen) m.getContainer().scrollIntoView({ block: "nearest", inline: "nearest" });
      popup.node.scrollTop = chosen
        ? popup.node.scrollTop + chosen.getBoundingClientRect().top - popup.node.getBoundingClientRect().top - 8
        : 0;
      const height =
        popup.node.parentElement?.getBoundingClientRect().height ||
        popup.node.offsetHeight;
      m.easeTo({
        center: panel.getLngLat(),
        zoom: Math.max(6, m.getZoom()),
        offset: [0, Math.min(mapHeight / 2 - 30, (height + 24) / 2)],
        duration: 250,
      });
      panel.setLngLat(panel.getLngLat());
    });
    return () => cancelAnimationFrame(frame);
  }, [popup, popupQuote]);
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
  const regions = departmentLabels(data.data?.points.map((p) => p.region) || []);
  const selectedInput = inputs.data?.find((input) => input.id === selected);
  const display = (p: MapPoint) =>
    p.unit.startsWith("COP") ? money(p.value) : number(p.value);
  const displayUnit = (p: MapPoint) => kind === "input"
      && wagePaymentBasis(selectedInput?.name || "", p.presentation || "")
    ? wageRateUnitDisplay(selectedInput!.name, p.presentation || "") : p.unit;
  const displayPresentation = (presentation: string) => kind === "input"
      && wagePaymentBasis(selectedInput?.name || "", presentation)
    ? wagePresentationDisplay(selectedInput!.name, presentation)
    : normalizeLabel(presentation, "presentation");
  const rankedPopupQuotes = [...(popup?.points || [])].sort((a, b) => b.value - a.value);
  const quoteKey = (point: MapPoint) => point.quote_key || point.id;
  const selectedPopupQuote = rankedPopupQuotes.find((p) => quoteKey(p) === popupQuote);
  const visiblePopupQuotes = rankedPopupQuotes.slice(0, 6);
  if (selectedPopupQuote && !visiblePopupQuotes.some((p) => quoteKey(p) === popupQuote))
    visiblePopupQuotes.push(selectedPopupQuote);
  return (
    <div className="map-workspace">
      <div className="map-controls"
        onFocusCapture={(event) => {
          searchFocused.current = (event.target as HTMLElement).getAttribute("aria-label") ===
            (kind === "input" ? "Elegir insumo en el mapa" : "Elegir producto en el mapa");
        }}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) searchFocused.current = false;
        }}>
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
          loading={kind === "input" ? inputs.loading : catalog.loading}
          error={Boolean(kind === "input" ? inputs.error : catalog.error)}
          onSelect={(o) => {
            bubble.current?.remove();
            setPopup(null);
            setSelected(o.id);
            setRegion("");
            if (kind !== "input" && o.id !== selected) {
              setRequested((current) => ({ ...current, series: "", market: "", presentation: "", units: "" }));
            }
          }}
        />
        {categoryPaths.length > 0 && <HierarchicalCategorySelect
          label="Categoría en mapa"
          value={requested.category || ""}
          paths={categoryPaths}
          onChange={(value) => {
            const compatible = !value || (kind === "input"
              ? (inputs.data || []).some((item) =>
                  resolveInputIdentity(item.id).canonicalId === selected &&
                  categoryMatches(item.category, value))
              : (catalog.data?.products || []).some((product) =>
                  product.id === selected && productCategoryPaths(product)
                    .some((path) => categoryMatches(path, value))));
            if (compatible) {
              changeFilter("category", value);
            } else {
              bubble.current?.remove();
              setPopup(null);
              setSelected("");
              setSearch("");
              setRequested((current) => ({
                ...current, category: value, market: "", presentation: "", units: "",
              }));
            }
          }}
        />}
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
          <SearchableSelect
            label="Presentación en mapa"
            value={filters.presentation || ""}
            options={quotePresentationOptions(data.data.options.presentations)}
            onChange={(value) => changeFilter("presentation", value)}
            allowClear={false}
          />
          <SearchableSelect
            label="Unidades en mapa"
            value={filters.units || ""}
            options={data.data.options.units.map((value) => ({ id: value, label: value }))}
            onChange={(value) => changeFilter("units", value)}
            allowClear={false}
          />
        </div>
      )}
      <AppliedFilters
        items={[
          {
            label: "Producto",
            value:
              kind === "input" && selectedInput
                ? `${selectedInput.name} · ${displayPresentation(selectedInput.presentation)}`
                : data.data?.selection_label ||
                  options.find((o) => o.id === selected)?.label ||
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
            value: mode !== "price" ? "" : kind === "input"
              ? displayPresentation(filters.presentation || selectedInput?.presentation || "")
              : normalizeLabel(filters.presentation || "", "presentation"),
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
                    )?.name || (filters.market ? "Mercado seleccionado" : "Todos")
                  : "Todos",
          },
          { label: "Departamento", value: filters.region || "Colombia" },
          { label: "Categoría", value: requested.category || "" },
          { label: "Búsqueda", value: filters.query || "" },
          {
            label: "Mes reportado",
            value: mode === "supply" && data.data?.period_start
              ? new Date(data.data.period_start + "T12:00:00Z").toLocaleDateString("es-CO", {
                month: "long", year: "numeric", timeZone: "America/Bogota",
              }) : "",
          },
          {
            label: "Historial",
            value: mode === "price"
              ? (filters.history || requested.history) === "all" ? "Todo el historial" : "Últimos 12 meses"
              : "",
          },
          {
            label: "Municipio",
            value: kind === "input" ? normalizeLabel(filters.municipality || "", "place") : "",
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
        <SearchableSelect
            label={mode === "supply" ? "Abrir abastecimiento de un departamento" : "Abrir precios de un departamento"}
            value={departmentLabel(region)}
            options={regions.map((value) => ({ id: value, label: value }))}
            emptyLabel="Toca un punto o departamento"
            onChange={(value) => {
              setRegion(value);
              const found =
                data.data?.points.filter((p) => !value || departmentKey(p.region) === departmentKey(value)) ||
                [];
              if (found.length) {
                const first = found[0];
                showPopup.current(found, value || "Colombia", [
                  first.longitude,
                  first.latitude,
                ]);
              }
            }}
        />
        <p>{data.data?.basis}</p>
      </div>
      {data.loading ? (
        <p role="status">Consultando el mapa…</p>
      ) : data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : !data.data?.points.length ? (
        <p className="empty-state">
          {mode === "supply" ? "No hay llegadas reportadas con ubicación para estos filtros." : "No hay precios con ubicación para estos filtros."}
        </p>
      ) : (
        <p className="map-hint">
          {data.data.points.length} {data.data.points.length === 1 ? "referencia" : "referencias"} · Toca un punto o departamento
          {" "}{mode === "supply" ? "para consultar su abastecimiento." : "para abrir sus precios."}
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
      <p className="privacy-note map-outline-note">
        Contornos departamentales orientativos; la procedencia del archivo no
        está verificada. Algunas islas pueden no estar representadas. El mapa
        no define linderos.
      </p>
      {popup &&
        createPortal(
          <>
            <h3>{popup.title}</h3>
            {popup.points.length > 6 && (
              <>
                <p>Se muestran seis referencias y la referencia elegida.</p>
                <SearchableSelect
                  label={mode === "supply" ? "Consultar abastecimiento en este lugar" : "Consultar precio en este lugar"}
                  placeholder="Busca referencia o mercado"
                  value={selectedPopupQuote ? popupQuote : ""}
                  options={rankedPopupQuotes.map((p) => ({
                    id: quoteKey(p), label: p.source_name || p.name,
                    detail: [display(p), displayUnit(p), p.date && dateLabel(p.date),
                      displayPresentation(p.presentation || ""), p.units].filter(Boolean).join(" · "),
                  }))}
                  onChange={setPopupQuote}
                />
              </>
            )}
            <div className="map-popup-quotes">
              {popup.points.length ? (
                visiblePopupQuotes.map((p) => (
                    <article key={quoteKey(p)} tabIndex={quoteKey(p) === popupQuote ? -1 : undefined} data-selected-quote={quoteKey(p) === popupQuote ? "true" : undefined}>
                      <strong>{p.name}</strong>
                      <span className="map-popup-price">{display(p)}</span>
                      {kind === "input" && p.source_name && <small>Nombre en la fuente: {p.source_name}</small>}
                      <small>{displayUnit(p)}</small>
                      {p.series === "city" && (
                        <>
                          <small>Punto medio calculado del rango</small>
                          {p.min_price != null && p.max_price != null && (
                            <small>Rango publicado: {money(p.min_price)}–{money(p.max_price)}</small>
                          )}
                        </>
                      )}
                      <small>{p.date && dateLabel(p.date)}</small>
                      {kind !== "input" && (
                        <a href={"/market/" + p.id}>Abrir mercado →</a>
                      )}
                      {mode === "supply" ? <SupplyMapEvidence point={p}
                        product={selected || undefined}
                        productName={options.find((option) => option.id === selected)?.label}
                      /> : <EvidenceLink
                        id={p.document_id}
                        page={p.source_page}
                        locator={p.source_locator}
                        input={kind === "input" ? p.source_input_id || selected : undefined}
                        product={kind === "product" ? selected : undefined}
                        productName={kind === "input"
                          ? p.source_name || inputs.data?.find((input) => input.id === selected)?.name
                          : options.find((option) => option.id === selected)?.label}
                        market={kind !== "input" ? p.id : undefined}
                        marketName={kind !== "input" ? p.name : undefined}
                        department={p.region}
                        municipality={p.municipality}
                        presentation={p.presentation}
                        units={p.units}
                        currency={p.unit.startsWith("COP /") ? "COP" : undefined}
                        month={p.date}
                      >
                        Consultar fuente
                      </EvidenceLink>}
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
