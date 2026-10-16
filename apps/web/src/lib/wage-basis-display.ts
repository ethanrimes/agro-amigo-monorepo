/** Display-only interpretation of an explicitly named DANE wage cadence.
 * Raw presentation values remain the selector and source-link values.
 */
export type WagePaymentBasis = "mes" | "semana" | "jornal";
type WageFamily = "agricola" | "pecuario";
type Meal = "con" | "sin";
type WageName = { basis: WagePaymentBasis; family: WageFamily; meal: Meal | null };
type WageInterpretation = { basis: WagePaymentBasis; meal: Meal | null };

function comparisonKey(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/gu, "")
    .toLocaleLowerCase("es-CO").replace(/\s+/gu, " ").trim();
}

function parseWageName(value: string): WageName | null {
  const match = /^(jornal|mensual|semanal) (agricola|pecuario)(?:(?:,\s+|\s+)(con|sin) alimentacion)?$/u.exec(comparisonKey(value));
  if (!match) return null;
  const basis: WagePaymentBasis = match[1] === "mensual" ? "mes"
    : match[1] === "semanal" ? "semana" : "jornal";
  return { basis, family: match[2] as WageFamily, meal: (match[3] as Meal | undefined) ?? null };
}

/**
 * Basis comes only from an exact agricultural/livestock cadence name. The
 * presentation must be the legacy "Jornal", a standalone printed meal label,
 * or the same full cadence/family with an explicit meal label.
 */
function interpretWage(name: string, presentation: string): WageInterpretation | null {
  const named = parseWageName(name);
  if (!named) return null;
  const foldedPresentation = comparisonKey(presentation);
  let presentationMeal: Meal | null = null;
  if (foldedPresentation === "jornal") {
    // Historical parser output stores every wage basis with raw unit "Jornal".
  } else if (foldedPresentation === "con alimentacion") {
    presentationMeal = "con";
  } else if (foldedPresentation === "sin alimentacion") {
    presentationMeal = "sin";
  } else {
    const presented = parseWageName(presentation);
    if (!presented || presented.basis !== named.basis || presented.family !== named.family || presented.meal === null)
      return null;
    presentationMeal = presented.meal;
  }
  if (named.meal !== null && presentationMeal !== null && named.meal !== presentationMeal)
    return null;
  return { basis: named.basis, meal: named.meal ?? presentationMeal };
}

function mealText(meal: Meal | null): string | null {
  return meal === "con" ? "con alimentación" : meal === "sin" ? "sin alimentación" : null;
}

export function wagePaymentBasis(name: string, presentation: string): WagePaymentBasis | null {
  return interpretWage(name, presentation)?.basis ?? null;
}

export function wagePresentationDisplay(name: string, presentation: string): string {
  const parsed = interpretWage(name, presentation);
  const friendlyBasis = parsed?.basis === "mes" ? "Pago mensual"
    : parsed?.basis === "semana" ? "Pago semanal"
      : parsed?.basis === "jornal" ? "Pago por jornal" : null;
  const meal = parsed ? mealText(parsed.meal) : null;
  return friendlyBasis ? `${friendlyBasis}${meal ? ` · ${meal}` : ""}` : presentation;
}

export function wageRateUnitDisplay(name: string, presentation: string): string {
  const parsed = interpretWage(name, presentation);
  const meal = parsed ? mealText(parsed.meal) : null;
  return parsed ? `COP / ${parsed.basis}${meal ? ` · ${meal}` : ""}` : `COP / ${presentation}`;
}

export function wageChartLabel(name: string, presentation: string): string {
  return interpretWage(name, presentation)
    ? wagePresentationDisplay(name, presentation)
    : `Precio por ${presentation}`;
}

export function wageBasisNote(name: string, presentation: string): string | null {
  const parsed = interpretWage(name, presentation);
  return parsed?.basis === "mes" ? "Pago mensual según el encabezado de la fuente"
    : parsed?.basis === "semana" ? "Pago semanal según el encabezado de la fuente"
      : parsed?.basis === "jornal"
        ? "La fuente identifica el valor por jornal; no especifica una duración en horas."
        : null;
}
