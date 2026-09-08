"use client";
import { EvidenceLink } from "@/components/planning/EvidenceLink";
import type { ComparisonKind, ComparisonQuote } from "@/lib/comparison-types";

export function quoteHref(
  q: ComparisonQuote,
  kind: ComparisonKind,
  history = "recent",
): string {
  const params: Record<string, string> =
    kind === "inputs"
      ? {
          department: q.department || "",
          municipality: q.municipality || "",
          scope: q.series === "input-municipal" ? "municipality" : "department",
          history,
        }
      : {
          market: q.location_id,
          series: q.series,
          presentation: q.presentation,
          units: q.units,
          history,
        };
  return `/${kind === "inputs" ? "insumo" : "product"}/${encodeURIComponent(q.id)}?${new URLSearchParams(params)}`;
}

export function QuoteEvidence({
  quote,
  kind,
}: {
  quote: ComparisonQuote;
  kind: ComparisonKind;
}) {
  const page =
    quote.source_page ||
    Number(quote.source_locator.match(/PDF page (\d+)/)?.[1]) ||
    undefined;
  return (
    <EvidenceLink
      id={quote.document_id}
      page={page}
      product={kind === "markets" ? quote.id : undefined}
      market={kind === "markets" ? quote.location_id : undefined}
      input={kind === "inputs" ? quote.id : undefined}
      department={quote.department}
      municipality={quote.municipality}
      month={quote.date}
    >
      Consultar fuente
    </EvidenceLink>
  );
}
