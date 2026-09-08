export const percentLabel = (n: number | null) =>
  n === null
    ? "Sin coincidencias"
    : `${n > 0 ? "+" : ""}${n.toLocaleString("es-CO", { maximumFractionDigits: 2 })} %`;
