export type Role = "farmer" | "buyer";
export type Product = {
  id: string;
  name: string;
  category: string;
  image_key: string;
  price: number;
  previous_price: number | null;
  date: string;
  market_count: number;
  unit: string;
  source: string;
  period: "daily" | "monthly";
};
export type MarketPrice = {
  id: string;
  name: string;
  city: string;
  region: string;
  price: number;
  min_price: number | null;
  max_price: number | null;
  date: string;
  source_url: string;
  document_id?: string;
  source_locator?: string;
  period: string;
  unit: string;
};
export type Point = { date: string; price: number };
export type Catalog = {
  products: Product[];
  regions: string[];
  latestDate: string | null;
  error?: string;
};
export type Coffee = {
  price: number;
  date: string;
  previous_price: number | null;
  source_url: string;
  document_id?: string;
  source_locator?: string;
  history: Point[];
  markets: MarketPrice[];
  factors: { factor: number; price: number; date: string }[];
  exchange: { price: number; date: string; source_url: string; document_id?: string } | null;
};
export const money = (value: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(value);
export const number = (value: number) =>
  new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(value);
export const dateLabel = (value: string, short = false) =>
  new Date(value.slice(0, 10) + "T12:00:00Z").toLocaleDateString("es-CO", {
    day: "numeric",
    month: short ? "short" : "long",
    year: short ? undefined : "numeric",
    timeZone: "America/Bogota",
  });
export const change = (now: number, previous: number | null) =>
  previous && previous > 0 ? ((now - previous) / previous) * 100 : null;
export const productImage = (key: string) =>
  `/images/${["coffee", "avocado", "tomato", "banana", "plantain", "potato"].includes(key) ? key : "produce"}.jpg`;
