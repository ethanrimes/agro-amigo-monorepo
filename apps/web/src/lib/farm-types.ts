import type { FarmProfile } from "./planning-types";
export type FarmPlan = {
  name: string;
  createdAt: string;
  period: string;
  periodCode: string;
  planYear: string;
  areaHa: number;
  yieldKgHa: number;
  lossPercent: number;
  uncertaintyPercent: number;
  costsPerHa: { label: string; amount: number; timing: "before" | "harvest" }[];
  costSource: {
    document: string;
    page: number;
    year: number;
    reviewed: boolean;
    templateId: string;
  } | null;
  extraSaleCost: number;
  commissionPercent: number;
  discountPercent: number;
  priceMode: "history" | "manual";
  productId: string;
  marketId: string;
  manualPrice: string;
  month: number;
  totalCost: number;
  breakEven: number | null;
  results:
    | {
        key: string;
        quantity: number;
        price: number;
        revenue: number;
        fees: number;
        profit: number;
      }[]
    | null;
  sourceDocuments: string[];
};
export type ManagedCrop = Pick<
  FarmProfile,
  | "cropCode"
  | "variety"
  | "area"
  | "stage"
  | "plantingDate"
  | "floweringDate"
  | "irrigation"
> & {
  id: string;
  name: string;
  yieldKgHa: string;
  planYear: string;
  physicalState: string;
  budget?: FarmPlan;
};
export type FarmRecord = {
  id: string;
  profile: FarmProfile;
  crops: ManagedCrop[];
  selectedCropId: string;
};
export type FarmStore = { version: 2; farms: FarmRecord[]; activeId: string };
export const FARM_STORAGE = "agroamigo-farms-v2";
export const EMPTY_PROFILE: FarmProfile = {
  municipalityId: "",
  name: "Mi finca",
  cropCode: "",
  variety: "",
  area: "1",
  stage: "planning",
  plantingDate: "",
  floweringDate: "",
  irrigation: false,
  latitude: "",
  longitude: "",
  elevation: "",
  locationMethod: "",
  locationAccuracy: "",
};
export function safeProfile(value: unknown): FarmProfile {
  const r =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  const p = { ...EMPTY_PROFILE };
  for (const key of Object.keys(p) as (keyof FarmProfile)[]) {
    if (key === "irrigation") p.irrigation = r.irrigation === true;
    else if (typeof r[key] === "string") p[key] = r[key].slice(0, 150);
  }
  return p;
}
export function cropFromProfile(
  p: FarmProfile,
  id = crypto.randomUUID(),
): ManagedCrop {
  return {
    id,
    cropCode: p.cropCode,
    name: p.variety || "Cultivo por completar",
    variety: p.variety,
    area: p.area,
    stage: p.stage,
    plantingDate: p.plantingDate,
    floweringDate: p.floweringDate,
    irrigation: p.irrigation,
    yieldKgHa: "",
    planYear: String(new Date().getFullYear()),
    physicalState: "",
  };
}
export function newFarm(p: FarmProfile, id = crypto.randomUUID()): FarmRecord {
  const crop = p.cropCode ? cropFromProfile(p) : null;
  return {
    id,
    profile: p,
    crops: crop ? [crop] : [],
    selectedCropId: crop?.id || "",
  };
}
export function profileFor(
  record: FarmRecord,
  cropId = record.selectedCropId,
): FarmProfile {
  const crop = record.crops.find((c) => c.id === cropId) || record.crops[0];
  return {
    ...record.profile,
    ...(crop
      ? {
          cropCode: crop.cropCode,
          variety: crop.variety,
          area: crop.area,
          stage: crop.stage,
          plantingDate: crop.plantingDate,
          floweringDate: crop.floweringDate,
          irrigation: crop.irrigation,
        }
      : {}),
  };
}
export function allocatedArea(record: FarmRecord) {
  return record.crops.reduce((sum, c) => sum + (Number(c.area) || 0), 0);
}
export function hasPin(p: FarmProfile) {
  return (
    p.latitude !== "" &&
    p.longitude !== "" &&
    Number.isFinite(+p.latitude) &&
    Number.isFinite(+p.longitude) &&
    +p.latitude >= -5 &&
    +p.latitude <= 14 &&
    +p.longitude >= -82 &&
    +p.longitude <= -66
  );
}
