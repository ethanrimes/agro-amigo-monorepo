import type { InputPrice, Evidence } from "./planning-types";

// Physically checked against the two columns on page 48 and the continuation
// on page 49. This is an annotation of one immutable original, not an alias.
const MARCH_2014_INPUTS = {
  id: "2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403",
  url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf",
  filename: "insumos_factores_de_produccion_mar_2014.pdf",
  bytes: 2028524,
};
const AGROTIN_PRESENTATION_NOTE =
  "Presentación literal de DANE: «Agrotin SL, 1 litro 1234» (páginas 48–49). " +
  "El mismo PDF también imprime «Agrotin SL, 1 litro» en otra columna. " +
  "Conservamos ambas referencias separadas; no hemos verificado que sean equivalentes.";

export function inputPresentationSourceNote(
  quote: Pick<InputPrice, "document_id" | "name" | "source_name" | "presentation">,
): string | null {
  if (quote.document_id !== MARCH_2014_INPUTS.id ||
      (quote.source_name || quote.name).trim().replace(/\s+/g, " ").toLowerCase() !== "agrotin sl" ||
      quote.presentation.trim().replace(/\s+/g, " ").toLowerCase() !== "1 litro 1234") return null;
  return AGROTIN_PRESENTATION_NOTE;
}

export function annotateInputSourceAmbiguity(evidence: Evidence): void {
  if (evidence.id === MARCH_2014_INPUTS.id && evidence.kind === "original" &&
      evidence.publisher === "DANE" && evidence.media_type === "application/pdf" &&
      evidence.source_url === MARCH_2014_INPUTS.url && evidence.bytes === MARCH_2014_INPUTS.bytes &&
      evidence.metadata.ingestion_kind === "context-pdf" &&
      evidence.metadata.original_filename === MARCH_2014_INPUTS.filename) {
    evidence.metadata.presentation_source_note = AGROTIN_PRESENTATION_NOTE;
  }
}
