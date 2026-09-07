/** Next.js does not emit the worker's sibling module. Both files are copied at build time. */
export async function mapLibrary() {
  const lib = await import("maplibre-gl");
  lib.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
  return lib;
}

export const mapSpanish = {
  "Map.Title": "Mapa",
  "NavigationControl.ZoomIn": "Acercar",
  "NavigationControl.ZoomOut": "Alejar",
  "NavigationControl.ResetBearing": "Orientar al norte",
  "AttributionControl.ToggleAttribution": "Ver créditos del mapa",
  "AttributionControl.MapFeedback": "Informar un problema del mapa",
  "FullscreenControl.Enter": "Pantalla completa",
  "FullscreenControl.Exit": "Salir de pantalla completa",
  "GeolocateControl.FindMyLocation": "Buscar mi ubicación",
  "GeolocateControl.LocationNotAvailable": "Ubicación no disponible",
  "LogoControl.Title": "Biblioteca de mapas MapLibre",
};
