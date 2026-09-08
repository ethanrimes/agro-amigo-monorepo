import type { LocationPoint } from "./location-types";
export type MapPlace = LocationPoint & { id: string; name: string; detail: string };
