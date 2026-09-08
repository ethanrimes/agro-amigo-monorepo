"use client";
import { useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { money, dateLabel } from "@/lib/market-types";
import type { ComparisonData, ComparisonRow } from "@/lib/comparison-types";
import { QuoteEvidence } from "./QuoteEvidence";
import styles from "./comparison.module.css";

export function ComparisonSources({
  row,
  context,
}: {
  row: ComparisonRow;
  context: ComparisonData;
}) {
  const [open, setOpen] = useState(false);
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
            <div className={styles.sourceList}>
              {sources.map((q) => (
                <div className={styles.sourceRow} key={q.location_id}>
                  <div>
                    <b>{q.location_name}</b>
                    <small>{dateLabel(q.date)}</small>
                    <QuoteEvidence quote={q} kind={context.kind} />
                  </div>
                  <strong>{money(q.price)}</strong>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </details>
  );
}
