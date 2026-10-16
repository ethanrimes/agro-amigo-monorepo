"use client";
import { useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { money, dateLabel } from "@/lib/market-types";
import { normalizeLabel } from "@/lib/label-normalization";
import { wagePaymentBasis, wagePresentationDisplay } from "@/lib/wage-basis-display";
import type { ComparisonData, ComparisonRow } from "@/lib/comparison-types";
import { QuoteEvidence } from "./QuoteEvidence";
import { SearchableSelect } from "@/components/ui/SearchableSelect";
import styles from "./comparison.module.css";

export function ComparisonSources({
  row,
  context,
}: {
  row: ComparisonRow;
  context: ComparisonData;
}) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const params = new URLSearchParams({
    ...context.filters,
    product: row.a.id,
    sources: "true",
  });
  const { data, loading, error, retry } = useData<ComparisonData>(
    open && !row.b?.sources ? `/api/compare/${context.kind}?${params}` : null,
  );
  const sources =
    row.b?.sources ||
    data?.rows.find((r) => r.key === row.key)?.b?.sources ||
    [];
  const sourceId = (source: typeof sources[number]) => JSON.stringify([
    source.location_id, source.document_id, source.source_locator, source.date,
    source.presentation, source.units,
  ]);
  const selected = sources.find((source) => sourceId(source) === selectedId);
  const sourceRow = (source: typeof sources[number]) => (
    <div className={styles.sourceRow} key={sourceId(source)}>
      <div>
        <b>{source.location_name}</b>
        <small>{dateLabel(source.date)}</small>
        <QuoteEvidence quote={source} kind={context.kind} />
      </div>
      <strong>{money(source.price)}</strong>
    </div>
  );
  return (
    <details
      className={styles.sources}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        Ver {row.b?.location_count} precios y fuentes del promedio
      </summary>
      {open && (
        <>
          {loading ? (
            <p role="status">Consultando las fuentes…</p>
          ) : error ? (
            <ErrorState message={error} retry={retry} />
          ) : (
            sources.length <= 6 ? (
              <div className={styles.sourceList}>
                {sources.map(sourceRow)}
              </div>
            ) : (
              <div>
                <SearchableSelect
                  label="Consultar una ubicación del promedio"
                  placeholder="Busca ubicación, fecha o unidad…"
                  value={selectedId}
                  options={sources.map((source) => ({
                    id: sourceId(source),
                    label: source.location_name,
                    detail: `${dateLabel(source.date)} · ${context.kind === "inputs"
                      && wagePaymentBasis(source.name, source.presentation)
                      ? wagePresentationDisplay(source.name, source.presentation)
                      : `${normalizeLabel(source.presentation, "presentation")} · ${source.units || source.unit}`}`,
                    searchText: [source.location_name, source.department, source.municipality,
                      source.date, source.presentation, source.units, source.unit, source.source_locator]
                      .filter(Boolean).join(" "),
                  }))}
                  onChange={setSelectedId}
                  emptyLabel="Busca y elige una ubicación exacta"
                />
                {selected && <div className={styles.sourceList}>{sourceRow(selected)}</div>}
              </div>
            )
          )}
        </>
      )}
    </details>
  );
}
