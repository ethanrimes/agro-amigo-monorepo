/** Source-backed equivalence for this complete 25 × 500 g city package. */
export const ARROZ_25X500G = "25 × 500 g";

export function cityPackageMatchSql(row = "r", document = "d") {
  return `(${row}.product_id='arroz-de-primera'
    AND ${row}.market_name='Cali, Santa Elena'
    AND lower(btrim(${row}.presentation))='bolsa'
    AND ${row}.quantity=25
    AND lower(btrim(${row}.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(${row}.unit))=lower(btrim(${row}.source_unit))
    AND ${row}.source_locator IS NOT NULL AND ${row}.source_locator<>''
    AND ${document}.id=${row}.document_id AND ${document}.kind='original'
    AND ${document}.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(${document}.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(${document}.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/')))`;
}

/** Dated revision identity keeps the prior normalized raw spelling semantics.
 * Only the source-guarded singular/plural package shares a new identity.
 */
export function cityDatedIdentityUnitSql(row = "r", document = "d") {
  return `CASE WHEN ${cityPackageMatchSql(row, document)} THEN '${ARROZ_25X500G}'
    ELSE lower(btrim(${row}.source_unit)) END`;
}

export function cityFilterUnitsSql(row = "r", document = "d") {
  return `CASE WHEN ${cityPackageMatchSql(row, document)} THEN '${ARROZ_25X500G}'
    ELSE ${row}.quantity::float8::text || ' ' || upper(left(${row}.source_unit,1)) || lower(substr(${row}.source_unit,2)) END`;
}

/** Comparison basis stays per complete package; never convert this to kg. */
export function cityComparisonUnitSql(row = "r", document = "d") {
  return `CASE WHEN ${cityPackageMatchSql(row, document)} THEN '${ARROZ_25X500G}' ELSE ${row}.unit END`;
}

/** Preserve old literal deep links only for a fully identified, available city package.
 * If its exact guarded option is absent, keep the old literal selection unavailable
 * instead of silently selecting a different package size.
 */
export function incomingCityPackageUnits(
  productId: string, marketId: string, presentation: string, requested: string,
  options: { series: string; market_id: string; market_name: string; presentation: string; units: string }[],
): string | undefined {
  if (productId !== "arroz-de-primera" || !/^25 unidad(?:es)? 500 gr$/i.test(requested.trim())) return undefined;
  const exact = options.some((option) => option.series === "city" && marketId !== "" &&
    option.market_id === marketId && option.market_name === "Cali, Santa Elena" &&
    option.presentation.toLocaleLowerCase() === presentation.toLocaleLowerCase() &&
    presentation.toLocaleLowerCase() === "bolsa" && option.units === ARROZ_25X500G);
  return exact ? ARROZ_25X500G : requested;
}
