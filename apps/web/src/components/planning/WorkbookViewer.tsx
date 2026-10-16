"use client";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/components/marketplace/useData";
import { ErrorState } from "@/components/marketplace/Shared";
import { workbookCellText, WORKBOOK_PREVIEW_VERSION, WORKBOOK_REQUEST_TIMEOUT_MS, type WorkbookCell } from "@/lib/workbook-cell";
import { SearchableSelect } from "@/components/ui/SearchableSelect";

type Workbook = {
  sheets: string[];
  sheet: string;
  start: number;
  totalRows: number;
  totalColumns: number;
  displayedColumns: number;
  rows: WorkbookCell[][];
  readOnly: true;
};
function columnLabel(index: number): string {
  let label = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26))
    label = String.fromCharCode(65 + ((n - 1) % 26)) + label;
  return label;
}
export function WorkbookViewer({
  id,
  initialSheet = "",
  initialRow = 1,
  initialColumn = 0,
}: {
  id: string;
  initialSheet?: string;
  initialRow?: number;
  initialColumn?: number;
}) {
  const [sheet, setSheet] = useState(initialSheet),
    [start, setStart] = useState(initialRow),
    [zoom, setZoom] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { data, loading, error, retry } = useData<Workbook>(
    `/api/evidence/${id}/workbook?${new URLSearchParams({ sheet, start: String(start), format: WORKBOOK_PREVIEW_VERSION })}`,
    WORKBOOK_REQUEST_TIMEOUT_MS,
  );
  useEffect(() => {
    if (!data || !initialColumn || data.sheet !== initialSheet ||
        data.start > initialRow || initialRow >= data.start + data.rows.length) return;
    const container = scrollRef.current;
    const cell = container?.querySelector<HTMLElement>(".workbook-source-cell");
    if (!container || !cell) return;
    const viewport = container.getBoundingClientRect();
    const target = cell.getBoundingClientRect();
    container.scrollLeft += target.left - viewport.left - (viewport.width - target.width) / 2;
  }, [data, initialColumn, initialRow, initialSheet]);
  return (
    <section
      className="pdf-viewer workbook-viewer"
      aria-label="Visor de Excel de solo lectura"
    >
      <div className="pdf-toolbar workbook-toolbar">
        <strong>Excel · Solo lectura</strong>
        <SearchableSelect
          label="Hoja del archivo Excel"
          value={data?.sheet || sheet}
          options={(data?.sheets || (sheet ? [sheet] : [])).map((name) => ({ id: name, label: name }))}
          onChange={(value) => { if (value) { setSheet(value); setStart(1); } }}
          selectedLabel={data?.sheet || sheet || undefined}
          placeholder="Busca el nombre de la hoja"
          loading={loading}
          error={Boolean(error)}
          allowClear={false}
        />
        <label>
          Zoom
          <select
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
          >
            {[0.75, 1, 1.25, 1.5].map((v) => (
              <option key={v} value={v}>
                {v * 100}%
              </option>
            ))}
          </select>
        </label>
      </div>
      {loading ? (
        <p className="pdf-status" role="status">
          Abriendo hoja…
        </p>
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : (
        data && (
          <>
            <p className="workbook-range">
              Hoja {data.sheet} · Filas {data.start}–
              {Math.min(data.start + data.rows.length - 1, data.totalRows)} de{" "}
              {data.totalRows.toLocaleString("es-CO")} · {data.totalColumns}{" "}
              columnas
            </p>
            <div
              className="workbook-scroll"
              ref={scrollRef}
              tabIndex={0}
              aria-label="Contenido de la hoja; desplázate para ver las columnas"
            >
              <table style={{ fontSize: 14 * zoom }}>
                <thead>
                  <tr>
                    <th aria-label="Fila" />
                    {Array.from({ length: data.displayedColumns }, (_, i) => (
                      <th key={i} scope="col">
                        {columnLabel(i)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, i) => (
                    <tr key={i}>
                      <th scope="row">{data.start + i}</th>
                      {row.map((cell, c) => (
                        <td
                          key={c}
                          className={[
                            cell.type === "number" ? "numeric" : "",
                            data.sheet === initialSheet && data.start + i === initialRow && c + 1 === initialColumn ? "workbook-source-cell" : "",
                          ].filter(Boolean).join(" ")}
                          aria-label={data.sheet === initialSheet && data.start + i === initialRow && c + 1 === initialColumn
                            ? `Celda ${columnLabel(c)}${initialRow} de la fuente` : undefined}
                        >
                          {workbookCellText(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="workbook-paging">
              <button
                className="button secondary"
                disabled={start <= 1}
                onClick={() => setStart(Math.max(1, start - 100))}
              >
                ← Filas anteriores
              </button>
              <label>
                Ir a la fila
                <input
                  key={`${sheet}-${start}`}
                  aria-label="Ir a la fila"
                  type="number"
                  min="1"
                  max={data.totalRows}
                  defaultValue={start}
                  onKeyDown={(e) => {
                    if (e.key === "Enter")
                      setStart(
                        Math.max(
                          1,
                          Math.min(
                            data.totalRows,
                            Number(e.currentTarget.value) || 1,
                          ),
                        ),
                      );
                  }}
                  onBlur={(e) =>
                    setStart(
                      Math.max(
                        1,
                        Math.min(data.totalRows, Number(e.target.value) || 1),
                      ),
                    )
                  }
                />
              </label>
              <button
                className="button secondary"
                disabled={start + 100 > data.totalRows}
                onClick={() => setStart(start + 100)}
              >
                Siguientes filas →
              </button>
            </div>
            <p className="privacy-note">
              Se conserva el orden del archivo original. Las fórmulas muestran
              el resultado guardado por la fuente. Desliza horizontalmente para
              ver más columnas.
            </p>
            {data.totalColumns > data.displayedColumns && (
              <p className="inline-note">
                La vista muestra las primeras {data.displayedColumns} columnas.
                Puedes descargar el archivo completo.
              </p>
            )}
          </>
        )
      )}
    </section>
  );
}
