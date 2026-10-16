import type { Evidence, VariationDisagreementSource } from "../planning-types";

export type ValidatedDailyDateResolution = {
  archive_date: string;
  observation_date: string;
  printed_heading: string;
  basis?: string;
  corroborating_url: string;
  price_disagreements?: {
    product_name: string;
    market_name: string;
    workbook_price: number;
    companion_pdf_price: number;
  }[];
  corroborating_sha256?: string;
  excluded_disagreements?: {
    product: string;
    market: string;
    xls_price_cell: string;
    xls_variation_cell: string;
    xls_price_cop_per_kg: number;
    xls_variation_percent: number;
    pdf_page: number;
    pdf_variation_percent: number;
    policy: string;
  }[];
};

const JAN2020_VARIATION_SOURCE = {
  document_id: "73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72",
  source_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.xlsx",
  corroborating_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_07_2020.pdf",
  companion_pdf_sha256: "2bba2c3ed056b5d2624af824c2d845aadbb16cadb31ab29e3ca26475061abaec",
  policy: "Not used as a corroborating witness; preserve workbook variation literally.",
} as const;

function jan2020VariationDisagreement(evidence: Evidence, resolution: ValidatedDailyDateResolution) {
  if (evidence.id !== JAN2020_VARIATION_SOURCE.document_id || evidence.kind !== "original" ||
      evidence.source_url !== JAN2020_VARIATION_SOURCE.source_url ||
      evidence.media_type !== "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
      evidence.metadata.ingestion_kind !== "daily" ||
      resolution.archive_date !== "2020-01-07" || resolution.basis !== "native_year_typo" ||
      resolution.observation_date !== "2020-01-07" ||
      resolution.corroborating_url !== JAN2020_VARIATION_SOURCE.corroborating_url ||
      resolution.corroborating_sha256 !== JAN2020_VARIATION_SOURCE.companion_pdf_sha256 ||
      !Array.isArray(resolution.excluded_disagreements) || resolution.excluded_disagreements.length !== 1) return null;

  const [item] = resolution.excluded_disagreements;
  if (!item || typeof item !== "object" || item.product !== "Pepino cohombro" || item.market !== "Neiva, Surabastos" ||
      item.xls_price_cell !== "T14" || item.xls_variation_cell !== "U14" ||
      item.xls_price_cop_per_kg !== 1120 || item.xls_variation_percent !== -25.33 ||
      item.pdf_page !== 1 || item.pdf_variation_percent !== -25.53 ||
      item.policy !== JAN2020_VARIATION_SOURCE.policy ||
      !Number.isFinite(item.xls_variation_percent) || !Number.isFinite(item.pdf_variation_percent)) return null;

  return item;
}

/** Annotate a retained, independently validated daily original without rewriting it. */
export function annotateDailyDateResolution(
  evidence: Evidence,
  resolution: ValidatedDailyDateResolution,
): void {
  const differentArchiveDate = resolution.archive_date !== resolution.observation_date;
  const identicalOriginalMislink = resolution.basis?.startsWith("mislinked_identical_") === true;
  if (differentArchiveDate) {
    evidence.metadata.original_reference_period = evidence.reference_period;
    evidence.reference_period = resolution.observation_date;
    evidence.metadata.archive_reference_date = resolution.archive_date;
    evidence.metadata.date_resolution_note =
      `Fecha verificada de las observaciones: ${resolution.observation_date}. ` +
      `El enlace del archivo corresponde al ${resolution.archive_date}, pero el original imprime «${resolution.printed_heading}». ` +
      (identicalOriginalMislink ? "El mismo original figura en el archivo de la fecha verificada. " : "") +
      `La publicación oficial corroborante confirma la fecha verificada; esos precios no se atribuyen al ${resolution.archive_date}. ` +
      `Conservamos el original y la referencia del enlace sin cambios.`;
  } else {
    evidence.metadata.date_resolution_note =
      `Fecha verificada: ${resolution.observation_date}. El encabezado original dice «${resolution.printed_heading}». ` +
      "Corroboramos la fecha con otra publicación oficial de DANE.";
  }
  evidence.metadata.date_evidence_url = resolution.corroborating_url;
  if (resolution.price_disagreements?.length) {
    evidence.metadata.price_disagreement_note = resolution.price_disagreements.map((item) =>
      `${item.product_name}, ${item.market_name}: el anexo publica $${item.workbook_price.toLocaleString("es-CO")} y el boletín $${item.companion_pdf_price.toLocaleString("es-CO")}. Conservamos el precio literal del anexo; las dos publicaciones difieren.`,
    ).join(" ");
  }
  const variationDisagreement = jan2020VariationDisagreement(evidence, resolution);
  if (variationDisagreement) {
    const formatPercent = (value: number) => `${value.toFixed(2).replace("-", "−").replace(".", ",")} %`;
    evidence.metadata.variation_disagreement_note =
      `Para ${variationDisagreement.product} en ${variationDisagreement.market}, el anexo (Boletín diario!${variationDisagreement.xls_variation_cell}) informa ${formatPercent(variationDisagreement.xls_variation_percent)} y el boletín acompañante informa ${formatPercent(variationDisagreement.pdf_variation_percent)} en la página ${variationDisagreement.pdf_page}. ` +
      `Conservamos la variación literal del anexo; las publicaciones difieren.`;
    const sources: VariationDisagreementSource[] = [{
      label: "Boletín acompañante de DANE",
      document_id: JAN2020_VARIATION_SOURCE.companion_pdf_sha256,
      page: variationDisagreement.pdf_page,
      locator: `Página física ${variationDisagreement.pdf_page}: variación de ${variationDisagreement.product} en ${variationDisagreement.market} (${formatPercent(variationDisagreement.pdf_variation_percent)}); el anexo Boletín diario!${variationDisagreement.xls_variation_cell} indica ${formatPercent(variationDisagreement.xls_variation_percent)}.`,
    }];
    evidence.metadata.variation_disagreement_sources = sources;
  }
}

const AUG2019_VARIATION_SOURCE = {
  document_id: "5f908d72f6b60fd3cf3f331ea2ae9434aa026d5561609b1fe4e085b7cad2ec85",
  source_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_agosto_12_2019.xlsx",
  companion_pdf_sha256: "bed32e2c8fa86f5d29b9131049c3af027bef80815262ee5db329ad560418c25b",
} as const;

/** Add display metadata for one exact retained source; stored quotes remain untouched. */
export function annotateDailySourceVariation(evidence: Evidence): void {
  if (evidence.id !== AUG2019_VARIATION_SOURCE.document_id || evidence.kind !== "original" ||
      evidence.source_url !== AUG2019_VARIATION_SOURCE.source_url ||
      evidence.media_type !== "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
      evidence.metadata.ingestion_kind !== "daily") return;

  evidence.metadata.variation_disagreement_note =
    "Para Habichuela en Manizales, el anexo (Boletín diario!M12) informa una variación de −46,88 % y el boletín acompañante narra un descenso de 46,48 % en la página 1. Ambas publicaciones indican $1.020/kg. Conservamos las dos lecturas y no inferimos cuál variación es correcta.";
  const sources: VariationDisagreementSource[] = [{
    label: "Boletín acompañante de DANE",
    document_id: AUG2019_VARIATION_SOURCE.companion_pdf_sha256,
    page: 1,
    locator: "Página física 1, párrafo sobre Habichuela en Manizales",
  }];
  evidence.metadata.variation_disagreement_sources = sources;
}
