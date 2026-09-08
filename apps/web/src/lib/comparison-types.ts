export type ComparisonKind = "markets" | "inputs";
export type ComparisonLocation = {
  id: string;
  name: string;
  series?: string[];
};
export type ComparisonQuote = {
  id: string;
  name: string;
  category: string;
  category_path: string[];
  presentation: string;
  units: string;
  unit: string;
  series: string;
  location_id: string;
  location_name: string;
  department?: string;
  municipality?: string;
  brand?: string;
  registration?: string;
  product_line?: string;
  price: number;
  date: string;
  document_id: string;
  source_locator: string;
  source_page?: number;
  min_price?: number;
  max_price?: number;
};
export type ComparisonReference = {
  price: number;
  date_from: string;
  date_to: string;
  location_count: number;
  sources?: ComparisonQuote[];
};
export type ComparisonRow = {
  key: string;
  a: ComparisonQuote;
  b: ComparisonReference | null;
  difference: number | null;
  percent: number | null;
};
export type ComparisonSummary = {
  category: string;
  subcategory: string | null;
  count: number;
  percent: number;
};
export type ComparisonData = {
  kind: ComparisonKind;
  filters: {
    a: string;
    b: string;
    series: string;
    scope: string;
    history: string;
    dates: string;
    product: string;
  };
  locations: ComparisonLocation[];
  series: string[];
  a_name: string;
  b_name: string;
  rows: ComparisonRow[];
  matched: number;
  unmatched: number;
  percent: number | null;
  summaries: ComparisonSummary[];
};
