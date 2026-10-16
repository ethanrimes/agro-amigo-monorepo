/** Effective display path for a retained city quote. Only the verified
 * source-bound overlay may replace parser classification; raw classification
 * and source category remain ordered fallbacks.
 */
export function verifiedCityCategoryPathSql(overlay: string, classificationPath: string, raw: string): string {
  return `coalesce(string_to_array(${overlay}.corrected_category,' > '),${classificationPath},string_to_array(${raw}.category,' > '))`;
}
