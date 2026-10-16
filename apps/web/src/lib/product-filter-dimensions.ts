import { normalizeLabel } from "./label-normalization";
import { defaultProductPackage } from "./product-filter-defaults";
import { incomingCityPackageUnits } from "./server/city-package-equivalence";
import { resolveCityMarketId } from "./server/city-market-alias";
import type { QuoteMarketChoice } from "./quote-filter-options";

export type ProductFilterSelection = {
  series: string;
  market: string;
  presentation: string;
  units: string;
  history: string;
};

export type ProductFilterDimension = {
  series: string;
  market_id: string;
  market_name: string;
  presentation: string;
  units: string;
  first_report_on?: string | null;
  last_report_on?: string | null;
};

export type ProductFilterDimensions = {
  product_id: string;
  region: string;
  options: ProductFilterDimension[];
};

export type ResolvedProductFilters = {
  filters: ProductFilterSelection;
  options: {
    series: string[];
    presentations: string[];
    units: string[];
    markets: QuoteMarketChoice[];
  };
};

/** Only a successful response for this exact product and region may supply
 * choices while the next price request is pending or has failed. */
export function resolveProductFilterDimensions(
  dimensions: ProductFilterDimensions | undefined,
  productId: string,
  region: string,
  requested: ProductFilterSelection,
): ResolvedProductFilters | null {
  if (!dimensions || dimensions.product_id !== productId || dimensions.region !== region)
    return null;
  const all = dimensions.options;
  const seriesOptions = [...new Set(all.map((option) => option.series))].sort(
    (a, b) => (a === "city" ? -1 : b === "city" ? 1 : a.localeCompare(b)),
  );
  const series = seriesOptions.includes(requested.series)
    ? requested.series : seriesOptions[0] || "monthly";
  const market = series === "city"
    ? resolveCityMarketId(requested.market) : requested.market;
  const presentations = [...new Set(all
    .filter((option) => option.series === series).map((option) => option.presentation))];
  const preferred = defaultProductPackage(all, series, market,
    requested.presentation, requested.units);
  const presentation = preferred.presentation;
  const unitsOptions = [...new Set(all
    .filter((option) => option.series === series && option.presentation === presentation)
    .map((option) => option.units))];
  const legacyUnits = incomingCityPackageUnits(
    productId, requested.series === "city" ? requested.market : "",
    requested.presentation, requested.units, all,
  );
  const units = legacyUnits || preferred.units;
  const matchingMarkets = new Map(all
    .filter((option) => option.series === series &&
      option.presentation === presentation && option.units === units)
    .map((option) => [option.market_id, {
      id: option.market_id,
      name: option.market_name,
      first_report_on: option.first_report_on ?? null,
      last_report_on: option.last_report_on ?? null,
    }]));
  const unavailableMarket = market && !matchingMarkets.has(market)
    ? all.find((option) => option.market_id === market) : undefined;
  if (unavailableMarket) matchingMarkets.set(market, {
    id: market,
    name: unavailableMarket.market_name + " · sin reportes para estos filtros",
    first_report_on: null,
    last_report_on: null,
  });
  return {
    filters: { series, presentation, units, market,
      history: requested.history === "all" ? "all" : "recent" },
    options: { series: seriesOptions, presentations, units: unitsOptions,
      markets: [...matchingMarkets.values()].map((option) => ({ ...option,
        literal_name: option.name,
        name: normalizeLabel(option.name, "place"),
      })) },
  };
}

export function marketReportsForUnits(
  dimensions: ProductFilterDimensions | undefined,
  productId: string,
  region: string,
  series: string,
  presentation: string,
  units: string,
  market: string,
): boolean {
  if (!market || !dimensions || dimensions.product_id !== productId || dimensions.region !== region)
    return false;
  const normalizedMarket = series === "city" ? resolveCityMarketId(market) : market;
  return dimensions.options.some((option) => option.series === series &&
    option.presentation === presentation && option.units === units &&
    option.market_id === normalizedMarket);
}
