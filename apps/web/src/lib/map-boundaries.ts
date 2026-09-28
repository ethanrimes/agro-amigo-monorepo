import type { FeatureCollection, Geometry, Position } from "geojson";

function validRing(ring: Position[]): boolean {
  if (!Array.isArray(ring) || ring.length < 4) return false;
  if (ring.some((p) => !Array.isArray(p) || p.length < 2 ||
    !Number.isFinite(p[0]) || !Number.isFinite(p[1]) ||
    Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90)) return false;
  const first = ring[0], last = ring[ring.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) return false;
  if (new Set(ring.map(([x, y]) => `${x},${y}`)).size < 3) return false;
  // Reject zero-area outlines; never close, relocate or invent coordinates.
  const area = ring.slice(1).reduce((sum, p, i) =>
    sum + ring[i][0] * p[1] - p[0] * ring[i][1], 0);
  return area !== 0;
}

/** Visual outline validation only: neither provenance nor cadastral accuracy. */
export function departmentOutlines(source: FeatureCollection<Geometry>) {
  if (source?.type !== "FeatureCollection" || !Array.isArray(source.features))
    throw new Error("Invalid department outlines");
  let rejectedPolygons = 0;
  const validPolygon = (rings: Position[][]) => {
    const valid = Array.isArray(rings) && rings.length > 0 && rings.every(validRing);
    if (!valid) rejectedPolygons++;
    return valid;
  };
  const features = source.features.flatMap((feature) => {
    const geometry = feature.geometry;
    if (geometry?.type === "Polygon")
      return validPolygon(geometry.coordinates) ? [feature] : [];
    if (geometry?.type === "MultiPolygon") {
      const coordinates = geometry.coordinates.filter(validPolygon);
      return coordinates.length ? [{ ...feature, geometry: { ...geometry, coordinates } }] : [];
    }
    return [];
  });
  return { data: { ...source, features }, rejectedPolygons };
}
