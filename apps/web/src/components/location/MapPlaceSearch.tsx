"use client";
import { useEffect, useState } from "react";
import { SearchBox } from "@/components/ui/SearchBox";
import { useData } from "@/components/marketplace/useData";
import type { Municipality } from "@/lib/planning-types";
import type { MapPlace } from "@/lib/place-types";
import { fold } from "@/lib/planning-math";
export function MapPlaceSearch({ onSelect }: { onSelect: (place: MapPlace) => void }) {
  const [query, setQuery] = useState(""), [remote, setRemote] = useState<MapPlace[]>([]);
  const [loading, setLoading] = useState(false), [message, setMessage] = useState("");
  const [selected, setSelected] = useState("");
  const municipalities = useData<Municipality[]>("/api/planning/municipalities");
  useEffect(() => {
    setRemote([]); setMessage(""); setLoading(false);
    if (query.trim().length < 3 || query === selected) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      fetch(`/api/location/search?q=${encodeURIComponent(query.trim().slice(0, 120))}`, { signal: controller.signal })
        .then(async r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => { if (!controller.signal.aborted) setRemote(data.places); })
        .catch(() => { if (!controller.signal.aborted) setMessage("No pudimos buscar otros lugares. Usa un municipio o explora el mapa."); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 650);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, selected]);
  const local: MapPlace[] = (municipalities.data || [])
    .filter(p => fold(`${p.name} ${p.department}`).includes(fold(query)))
    .slice(0, 5).map(p => ({ id: `municipality-${p.id}`, name: p.name, detail: `${p.department} · Municipio`, latitude: p.latitude, longitude: p.longitude }));
  const options = [...local, ...remote];
  return <div className="panel map-place-search">
    <SearchBox label="Buscar un lugar en el mapa" placeholder="Municipio, vereda, mercado o lugar cercano…" value={query}
      onChange={setQuery} filterOptions={false}
      options={options.map(p => ({ id: p.id, label: p.name, detail: p.detail }))}
      onSelect={option => { const p = options.find(p => p.id === option.id); if (p) { setSelected(p.name); onSelect(p); } }} />
    <p className="field-help">Busca un lugar, acerca el mapa y toca donde está tu finca. Luego elige «Fijar mi pin aquí».</p>
    {loading && <p role="status">Buscando lugares…</p>}
    {message && <p role="status">{message}</p>}
    <small>Lugares: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a> vía Photon. La búsqueda puede no incluir todas las veredas; puedes ubicar el pin en el mapa.</small>
  </div>;
}
