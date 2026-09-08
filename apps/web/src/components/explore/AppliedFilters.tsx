"use client";
export function AppliedFilters({
  items,
}: {
  items: { label: string; value: string; clear?: () => void }[];
}) {
  return (
    <div className="applied-filters" aria-label="Filtros aplicados">
      <span>Consulta actual</span>
      {items
        .filter((i) => i.value)
        .map((i) => (
          <span className="filter-chip" key={i.label}>
            <b>{i.label}:</b> {i.value}
            {i.clear && (
              <button onClick={i.clear} aria-label={`Quitar filtro ${i.label}`}>
                ×
              </button>
            )}
          </span>
        ))}
    </div>
  );
}
export const priceSeriesLabel: Record<string, string> = {
  city: "Informe por ciudad · diario",
  monthly: "Promedio mayorista · mensual",
  farmgate: "Leche en finca · mensual",
  mill: "Arroz en molino · mensual",
  coffee: "Referencia FNC",
};
