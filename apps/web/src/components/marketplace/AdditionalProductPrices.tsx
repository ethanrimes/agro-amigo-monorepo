"use client";

import Link from "next/link";
import { dateLabel } from "@/lib/market-types";
import { officialMoney, type OfficialPrice } from "@/lib/official-types";

export function AdditionalProductPrices({ rows }: { rows: OfficialPrice[] }) {
  if (!rows.length) return null;
  return (
    <details className="panel">
      <summary>Más precios y fuentes disponibles ({rows.length})</summary>
      <p>Cada opción abre una consulta con el mercado y la unidad indicados.</p>
      <div className="entity-price-list">
        {rows.map((row) => (
          <article key={row.quote_key}>
            <div>
              <Link href={"/references/" + row.quote_key}>{row.market}</Link>
              <small>{row.basis} · {row.publisher}</small>
              <small>{dateLabel(row.observed_on)}</small>
            </div>
            <div>
              <strong>{officialMoney(row.price, row.currency)}</strong>
              <small>Por {row.unit}</small>
              <Link href={"/references/" + row.quote_key}>Ver precio y fuente →</Link>
            </div>
          </article>
        ))}
      </div>
    </details>
  );
}
