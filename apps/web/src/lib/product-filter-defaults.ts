/** Source-backed report dates choose defaults; all older dimensions remain visible. */
export type DatedPackageOption = {
  series: string;
  market_id: string;
  presentation: string;
  units: string;
  last_report_on?: string | null;
};

function latest<T extends DatedPackageOption>(options: T[]): T | undefined {
  let chosen: T | undefined;
  for (const option of options) {
    // A missing date (ordinary monthly sources) retains the existing order.
    if (!chosen || (option.last_report_on || "") > (chosen.last_report_on || ""))
      chosen = option;
  }
  return chosen;
}

/** Default missing or unavailable package filters. An explicit available package remains selected,
 * even when its last report predates the recent window. A requested market
 * constrains defaults when it has options; it is never silently replaced. */
export function defaultProductPackage<T extends DatedPackageOption>(
  options: T[], series: string, market: string,
  requestedPresentation: string, requestedUnits: string,
): { presentation: string; units: string } {
  const inSeries = options.filter((option) => option.series === series);
  const inMarket = market ? inSeries.filter((option) => option.market_id === market) : [];
  const preferred = inMarket.length ? inMarket : inSeries;
  const presentation = inSeries.find((option) =>
    option.presentation.toLocaleLowerCase() === requestedPresentation.toLocaleLowerCase()
  )?.presentation || latest(preferred)?.presentation || "";
  const unitsInPresentation = inSeries.filter((option) => option.presentation === presentation);
  const unitsInMarket = inMarket.filter((option) => option.presentation === presentation);
  const units = unitsInPresentation.find((option) => option.units === requestedUnits)?.units ||
    latest(unitsInMarket.length ? unitsInMarket : unitsInPresentation)?.units || "";
  return { presentation, units };
}
