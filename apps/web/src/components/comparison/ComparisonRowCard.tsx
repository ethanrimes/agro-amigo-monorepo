"use client";
import Link from "next/link";
import { money, dateLabel } from "@/lib/market-types";
import type { ComparisonData, ComparisonRow } from "@/lib/comparison-types";
import { ComparisonSources } from "./ComparisonSources";
import { QuoteEvidence, quoteHref } from "./QuoteEvidence";
import { percentLabel } from "./format";
import styles from "./comparison.module.css";

export function ComparisonRowCard({
  row,
  context,
}: {
  row: ComparisonRow;
  context: ComparisonData;
}) {
  const kind = context.kind;
  return (
    <article className={styles.row}>
      <div className={styles.rowHead}>
        <div>
          <Link href={quoteHref(row.a, kind, context.filters.history)}>
            {row.a.name}
          </Link>
          <p>{row.a.category_path.join(" > ")}</p>
          <p>
            {row.a.presentation}
            {row.a.units !== row.a.presentation ? ` · ${row.a.units}` : ""}
          </p>
          {(row.a.brand || row.a.registration) && (
            <p className={styles.identity}>
              {row.a.brand}
              {row.a.registration ? ` · ICA ${row.a.registration}` : ""}
            </p>
          )}
        </div>
        <div
          className={`${styles.difference} ${row.percent !== null && row.percent > 0 ? styles.up : styles.down}`}
        >
          {percentLabel(row.percent)}
          {row.difference !== null && (
            <p className={styles.muted}>
              {row.difference > 0 ? "+" : ""}
              {money(row.difference)}
            </p>
          )}
        </div>
      </div>
      <div className={styles.prices}>
        <div className={styles.price}>
          <span>A · {context.a_name}</span>
          <strong>{money(row.a.price)}</strong>
          <small>{dateLabel(row.a.date)}</small>
          <QuoteEvidence quote={row.a} kind={kind} />
        </div>
        <div className={styles.price}>
          <span>B · {context.b_name}</span>
          <strong>{row.b ? money(row.b.price) : "Sin dato equivalente"}</strong>
          {row.b && (
            <>
              <small>
                {row.b.date_from === row.b.date_to
                  ? dateLabel(row.b.date_to)
                  : `${dateLabel(row.b.date_from)} – ${dateLabel(row.b.date_to)}`}
              </small>
              {row.b.location_count > 1 ? (
                <small>
                  {row.b.location_count} lugares con la misma combinación
                </small>
              ) : (
                row.b.sources?.[0] && (
                  <QuoteEvidence quote={row.b.sources[0]} kind={kind} />
                )
              )}
            </>
          )}
        </div>
      </div>
      {row.b && row.b.location_count > 1 && (
        <ComparisonSources row={row} context={context} />
      )}
    </article>
  );
}
