export type OfficialPrice = {
  quote_key: string;
  product_id: string;
  product_name: string;
  category: string;
  publisher: string;
  series: string;
  basis: string;
  currency: string;
  unit: string;
  market: string;
  observed_on: string;
  period_start: string | null;
  price: number;
  min_price: number | null;
  max_price: number | null;
  source_page?: number;
  document_id: string;
  source_locator: string;
  source_url: string;
  details: Record<string, unknown>;
};
export function officialMoney(value: number, currency: string) {
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    maximumFractionDigits: currency === "COP" ? 2 : 4,
  }).format(value);
}
export const officialDetailLabels: Record<string, string> = {
  source_product: "Nombre en la publicación",
  source_description: "Descripción de la referencia",
  underlying_sources: "Fuentes del indicador",
  variety: "Variedad y características",
  origin: "Origen",
  original_quote: "Cotización publicada",
  original_period: "Período publicado",
  original_price: "Precio publicado",
  change_percent: "Variación mensual (%)",
  period_type: "Frecuencia",
  period_end: "Fin del período",
  source_note: "Nota de la fuente",
  presentation: "Presentación",
  quantity: "Cantidad",
  published_unit: "Unidad publicada",
  quality: "Calidad",
  statistic: "Medida publicada",
  methodology_change: "Fecha de cambio de método",
  grade: "Clasificación",
  mostly_min: "Precio habitual mínimo",
  mostly_max: "Precio habitual máximo",
  market_description: "Descripción del mercado",
};
