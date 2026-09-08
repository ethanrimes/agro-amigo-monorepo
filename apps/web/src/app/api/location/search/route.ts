import { NextRequest, NextResponse } from "next/server";
import { inColombia } from "@/lib/location-types";
import type { MapPlace } from "@/lib/place-types";
export const dynamic = "force-dynamic";
const cache = new Map<string, { expires: number; places: MapPlace[] }>();
const pending = new Map<string, Promise<MapPlace[]>>();
async function search(query: string): Promise<MapPlace[]> {
  // Configurable so a hosted/private Photon service can replace the demo.
  const url = new URL(process.env.PHOTON_SEARCH_URL || "https://photon.komoot.io/api/");
  url.search = new URLSearchParams({ q: query, limit: "8", bbox: "-82,-5,-66,14", countrycode: "CO" }).toString();
  const response = await fetch(url, {
    signal: AbortSignal.timeout(8000), cache: "no-store",
    headers: { "User-Agent": "AgroAmigo-demo/1.0 (place search)" },
  });
  if (!response.ok) throw new Error("GEOCODER_UNAVAILABLE");
  const raw = await response.text();
  if (raw.length > 100_000) throw new Error("GEOCODER_SCHEMA");
  const data = JSON.parse(raw);
  if (!Array.isArray(data.features)) throw new Error("GEOCODER_SCHEMA");
  return data.features.slice(0, 8).flatMap((feature: {
    geometry?: { type: string; coordinates: unknown[] };
    properties?: Record<string, unknown>;
  }) => {
    const p = feature.properties, coords = feature.geometry?.coordinates;
    if (!p || feature.geometry?.type !== "Point" || !coords ||
      typeof coords[0] !== "number" || typeof coords[1] !== "number") return [];
    const point = { latitude: coords[1], longitude: coords[0] };
    if (!inColombia(point) || String(p.countrycode).toUpperCase() !== "CO") return [];
    const name = typeof p.name === "string" ? p.name : typeof p.street === "string" ? p.street : "";
    if (!name) return [];
    const detail = [...new Set([p.district, p.city, p.county, p.state].filter(x => typeof x === "string" && x !== name))].join(", ");
    return [{ ...point, id: `osm-${p.osm_type}-${p.osm_id}`, name, detail }];
  });
}
export async function GET(req: NextRequest) {
  const query = (req.nextUrl.searchParams.get("q") || "").trim();
  if (query.length < 3 || query.length > 120)
    return NextResponse.json({ places: [] }, { status: 400 });
  const key = query.toLocaleLowerCase("es-CO"), saved = cache.get(key);
  if (saved && saved.expires > Date.now()) return NextResponse.json({ places: saved.places });
  if (!pending.has(key) && pending.size >= 2)
    return NextResponse.json({ error: "La búsqueda está ocupada. Intenta de nuevo." }, { status: 429 });
  let task = pending.get(key);
  if (!task) {
    task = search(query); pending.set(key, task);
    void task.finally(() => pending.delete(key)).catch(() => {});
  }
  try {
    const places = await task;
    if (cache.size >= 500) cache.delete(cache.keys().next().value!);
    cache.set(key, { expires: Date.now() + 86400_000, places });
    return NextResponse.json({ places }, { headers: { "Cache-Control": "private, max-age=3600" } });
  } catch {
    return NextResponse.json({ error: "No pudimos buscar otros lugares. Puedes buscar un municipio o explorar el mapa." }, { status: 503 });
  }
}
