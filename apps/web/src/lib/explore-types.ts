import type { Product, Point } from "./market-types";
import type { InputPrice } from "./planning-types";
export type Market = {
  id: string;
  name: string;
  city: string;
  region: string;
  municipality_id: string | null;
  latitude: number | null;
  longitude: number | null;
  department_id: string | null;
  product_count: number;
  date: string | null;
  supply_date: string | null;
};
export type MarketDetail = {
  market: Market;
  products: (Product & { document_id: string; source_locator: string })[];
};
export type InputDetail = {
  input: InputPrice;
  regions: InputPrice[];
  history: Point[];
};
export type SupplyRow = {
  market_id: string;
  market_name: string;
  region: string;
  food_id: string;
  food_name: string;
  product_id: string | null;
  period_start: string;
  observed_on: string;
  first_reported_on: string;
  quantity_kg: number;
  document_id: string;
  reporting_days: number;
};
export type SupplyData = {
  rows: SupplyRow[];
  history: { date: string; quantity_kg: number }[];
  latest_period: string | null;
  selected_period: string | null;
};
export type MapPoint = {
  id: string;
  name: string;
  region: string;
  department_id: string;
  latitude: number;
  longitude: number;
  value: number;
  date: string;
  unit: string;
  document_id?: string;
  source_page?: number;
  source_locator?: string;
  presentation?: string;
  units?: string;
};
export type MapFilters = {
  series?: string;
  market?: string;
  presentation?: string;
  units?: string;
  history?: string;
  region?: string;
  scope?: string;
  municipality?: string;
  category?: string;
  query?: string;
};
export type MapData = {
  selection_label?: string;
  points: MapPoint[];
  unit: string;
  date: string | null;
  basis: string;
  filters?: MapFilters;
  options?: {
    series: string[];
    presentations: string[];
    units: string[];
    markets: { id: string; name: string }[];
  };
};
