"use client";

import { useState } from "react";
import { EvidenceLink } from "./EvidenceLink";
import { dateLabel, number } from "@/lib/market-types";
import { SearchableSelect } from "../ui/SearchableSelect";

type RowRange = [number, number];

function sheetRanges(value: unknown): [string, RowRange[]][] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).flatMap(([sheet, ranges]) => {
    if (!Array.isArray(ranges)) return [];
    const valid = ranges.filter((range): range is RowRange =>
      Array.isArray(range) && range.length === 2 &&
      Number.isInteger(range[0]) && Number.isInteger(range[1]) &&
      range[0] > 0 && range[1] >= range[0],
    );
    return valid.length ? [[sheet, valid] as [string, RowRange[]]] : [];
  });
}

/** Keep every contributing interval reachable without a long scrolling table. */
function OriginalSupplyRows({ id, sheet, ranges, query }: {
  id: string;
  sheet: string;
  ranges: RowRange[];
  query: URLSearchParams;
}) {
  const [selected, setSelected] = useState("");
  const [start, end] = ranges.find(([a, b]) => `${a}:${b}` === selected) || ranges[0];
  return (
    <details>
      <summary>Hoja {sheet} · filas que forman el total</summary>
      <p>Busca una fila o intervalo para consultar sus celdas originales. Todos los {ranges.length} intervalos están disponibles.</p>
      <SearchableSelect
        label={`Filas originales de la hoja ${sheet}`}
        value={`${start}:${end}`}
        options={ranges.map(([a, b]) => ({
          id: `${a}:${b}`,
          label: a === b ? `Fila ${a}` : `Filas ${a}–${b}`,
          detail: `Hoja ${sheet}`,
        }))}
        onChange={setSelected}
        allowClear={false}
      />
      <EvidenceLink id={id} sheet={sheet} row={start}
        department={query.get("department") || undefined}
        municipality={query.get("municipality") || undefined}
        product={query.get("product") || undefined}
        productName={query.get("productName") || undefined}
        market={query.get("market") || undefined}
        marketName={query.get("marketName") || undefined}
        units={query.get("units") || undefined}
        food={query.get("food") || undefined}
        month={query.get("month") || undefined}>
        Ver fila {start} →
      </EvidenceLink>
    </details>
  );
}

/** A monthly sum has many original rows, rather than one source cell. */
export function SupplyEvidenceRecords({ id, records, query }: {
  id: string;
  records?: Record<string, unknown>[];
  query: URLSearchParams;
}) {
  const selected = records?.filter((record) =>
    typeof record.quantity_kg === "number" &&
    typeof record.reporting_days === "number" &&
    typeof record.food_name === "string",
  );
  if (!selected?.length) return null;
  return (
    <section className="panel evidence-records" data-testid="selected-supply-records">
      <h2>Abastecimiento de esta consulta</h2>
      <p>El total del período suma los registros del archivo original. Un día puede tener varios registros; los días con reporte se cuentan una sola vez.</p>
      {selected.slice(0, 100).map((record, index) => {
        const sheets = sheetRanges(record.source_rows);
        const rowCount = sheets.reduce((total, [, ranges]) => total + ranges.reduce(
          (count, [start, end]) => count + end - start + 1, 0), 0);
        return (
          <details key={index} open={selected.length <= 3}>
            <summary>{String(record.food_name)} · {String(record.market_name || "Mercado consultado")}</summary>
            <dl>
              <div><dt>Cantidad total (kg)</dt><dd>{(record.quantity_kg as number).toLocaleString("es-CO", { maximumFractionDigits: 20 })}</dd></div>
              <div><dt>Equivalente en toneladas</dt><dd>{number((record.quantity_kg as number) / 1000)} t</dd></div>
              <div><dt>Días con reporte</dt><dd>{String(record.reporting_days)}</dd></div>
              {typeof record.period_start === "string" && <div><dt>Inicio del período</dt><dd>{dateLabel(record.period_start)}</dd></div>}
              {typeof record.first_reported_on === "string" && <div><dt>Primer reporte</dt><dd>{dateLabel(record.first_reported_on)}</dd></div>}
              {typeof record.observed_on === "string" && <div><dt>Último reporte</dt><dd>{dateLabel(record.observed_on)}</dd></div>}
              {rowCount > 0 && <div><dt>Registros originales que forman el total</dt><dd>{number(rowCount)}</dd></div>}
            </dl>
            {sheets.map(([sheet, ranges]) => (
              <OriginalSupplyRows key={sheet} id={id} sheet={sheet} ranges={ranges} query={query} />
            ))}
          </details>
        );
      })}
      {selected.length > 100 && <p>Se muestran los primeros 100 registros consultados. Descarga el original para revisar el archivo completo.</p>}
    </section>
  );
}
