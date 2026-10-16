"use client";

import Link from "next/link";
import { useState } from "react";
import { dateLabel } from "@/lib/market-types";
import { officialMoney, type OfficialPrice } from "@/lib/official-types";
import { SearchableSelect } from "@/components/ui/SearchableSelect";

export function AdditionalProductPrices({ rows }: { rows: OfficialPrice[] }) {
  const [selectedQuote, setSelectedQuote] = useState("");
  if (!rows.length) return null;
  const searchable = rows.length > 6;
  const selected = rows.find((row) => row.quote_key === selectedQuote);
  const visible = searchable ? selected ? [selected] : [] : rows;
  return (
    <details className="panel">
      <summary>Más precios y fuentes disponibles ({rows.length})</summary>
      <p>Cada referencia abre su propio precio y fuente, con el mercado, moneda y unidad publicados.</p>
      {searchable && (
        <SearchableSelect
          label="Consultar otra referencia y fuente"
          placeholder="Busca mercado, fuente o fecha…"
          emptyLabel="Busca y elige una referencia para ver su precio y fuente"
          value={selectedQuote}
          onChange={setSelectedQuote}
          selectedLabel={selectedQuote ? "Referencia ya no disponible" : undefined}
          options={rows.map((row) => ({
            id: row.quote_key,
            label: row.market,
            detail: `${row.publisher} · ${row.basis} · ${dateLabel(row.observed_on)} · ${officialMoney(row.price, row.currency)} por ${row.unit}`,
          }))}
        />
      )}
      <div className="entity-price-list">
        {visible.map((row) => (
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
