export type Municipality = {
  id: string;
  name: string;
  department: string;
  department_id: string;
  latitude: number;
  longitude: number;
  document_id: string;
};
export type FarmProfile = {
  municipalityId: string;
  name: string;
  cropCode: string;
  variety: string;
  area: string;
  stage: string;
  plantingDate: string;
  floweringDate: string;
  irrigation: boolean;
  latitude: string;
  longitude: string;
  elevation: string;
};
export type CropReference = {
  crop_code: string;
  crop: string;
  variety: string;
  reference_year: number;
  cycle: string;
  physical_state: string;
  planted_ha: number;
  harvested_ha: number;
  production_t: number;
  yield_kg_ha: number | null;
  document_id: string;
  source_rows: number[];
};
export type CalendarReference = {
  crop: string;
  activity: string;
  percentages: number[];
  reference_year: number;
  document_id: string;
  source_row: number;
};
export type Suitability = {
  crop_key: string;
  classification: string;
  area_ha: number;
  document_id: string;
  title: string;
  metadata: { description?: string; scale?: string };
};
export type SoilReference = {
  samples: number;
  ph_samples: number;
  ph_median: number | null;
  ph_low: number | null;
  ph_high: number | null;
  organic_matter_median: number | null;
  oldest: string | null;
  newest: string | null;
  document_id: string;
};
export type CostLine = {
  label: string;
  amount: number;
  timing: "before" | "harvest";
};
export type CostTemplate = {
  id: string;
  crop: string;
  title: string;
  region: string;
  municipalities: string[];
  reference_year: number;
  production_system: string;
  yield_kg_ha: number;
  costs: CostLine[];
  document_id: string;
  source_page: number;
  notes: string;
};
export type Advisory = {
  id: string;
  title: string;
  summary: string;
  action: string;
  crops: string[];
  departments: string[];
  published_on: string;
  valid_until: string | null;
  kind: "official_alert" | "monitoring" | "reference";
  document_id: string;
  source_page: number | null;
  source_url: string;
};
export type FarmData = {
  municipality: Municipality;
  crops: CropReference[];
  calendars: CalendarReference[];
  suitability: Suitability[];
  soil: SoilReference | null;
  templates: CostTemplate[];
  advisories: Advisory[];
};
export type WeatherDaily = {
  time: string[];
  weather_code: (number | null)[];
  temperature_2m_max: (number | null)[];
  temperature_2m_min: (number | null)[];
  precipitation_sum: (number | null)[];
  precipitation_probability_max: (number | null)[];
  wind_speed_10m_max: (number | null)[];
  et0_fao_evapotranspiration: (number | null)[];
};
export type Weather = {
  id: string;
  fetched_at: string;
  source_url: string;
  latitude: number;
  longitude: number;
  stale: boolean;
  payload: {
    latitude: number;
    longitude: number;
    elevation: number;
    daily: WeatherDaily;
    daily_units: Record<string, string>;
  };
};
export type Seasonality = {
  latest: { price: number; date: string; market: string } | null;
  years: {
    reference_year: number;
    monthly_prices: number[];
    document_id: string;
    source_rows: string[];
  }[];
  unit: string;
  method: string;
};
export type InputPrice = {
  id: string;
  name: string;
  department: string;
  category: string;
  presentation: string;
  price: number;
  previous_price: number | null;
  observed_on: string;
  document_id: string;
  source_locator: string;
};
export type Evidence = {
  id: string;
  title: string;
  publisher: string;
  source_url: string;
  media_type: string;
  kind: "original" | "extract" | "methodology";
  reference_period: string;
  retrieved_at: string;
  page_count: number | null;
  bytes: number;
  metadata: Record<string, unknown>;
  parents: { id: string; title: string }[];
  text?: string;
  records?: Record<string, unknown>[];
};
export type Offer = {
  id: string;
  name: string;
  price: string;
  acceptedKg: string;
  deductionPercent: string;
  transport: string;
  packaging: string;
  fees: string;
  paymentDays: string;
  expires: string;
  quality: string;
  pickup: boolean;
};
