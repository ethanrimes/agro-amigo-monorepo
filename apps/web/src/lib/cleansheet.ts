import { fold } from "./planning-math";
export type CleanCost = {
  label: string;
  amount: string;
  timing: "before" | "harvest";
};
export type CleanInputs = {
  area: string;
  yieldKg: string;
  loss: string;
  price: string;
  commission: string;
  delivery: string;
  costs: CleanCost[];
};
export function cleanResult(v: CleanInputs) {
  const fields = [
    v.area,
    v.yieldKg,
    v.loss,
    v.price,
    v.commission,
    v.delivery,
    ...v.costs.map((c) => c.amount),
  ];
  if (
    !v.costs.length ||
    fields.some((x) => x.trim() === "" || !Number.isFinite(+x) || +x < 0) ||
    +v.area <= 0 ||
    +v.area > 100000 ||
    +v.yieldKg <= 0 ||
    +v.yieldKg > 1000000 ||
    +v.loss >= 100 ||
    +v.commission >= 100 ||
    +v.price <= 0
  )
    return null;
  const quantity = +v.area * +v.yieldKg * (1 - +v.loss / 100),
    revenue = quantity * +v.price,
    production = v.costs.reduce((s, c) => s + +c.amount, 0) * +v.area,
    fees = (revenue * +v.commission) / 100,
    total = production + fees + +v.delivery;
  return {
    quantity,
    revenue,
    production,
    fees,
    total,
    profit: revenue - total,
    breakEven:
      (production + +v.delivery) / (quantity * (1 - +v.commission / 100)),
    before:
      v.costs
        .filter((c) => c.timing === "before")
        .reduce((s, c) => s + +c.amount, 0) * +v.area,
    costPerKg: production / quantity,
    margin: ((revenue - total) / revenue) * 100,
  };
}
export function waterfallRows(v: CleanInputs) {
  const r = cleanResult(v);
  if (!r) return [];
  let level = r.revenue;
  const rows = [
    {
      label: "Ingresos por venta",
      value: r.revenue,
      start: 0,
      end: r.revenue,
      kind: "revenue",
    },
  ];
  for (const c of [
    ...v.costs.map((c) => ({ label: c.label, value: +c.amount * +v.area })),
    { label: "Transporte y venta", value: +v.delivery },
    { label: "Comisiones", value: r.fees },
  ]) {
    rows.push({
      label: c.label,
      value: c.value === 0 ? 0 : -c.value,
      start: level,
      end: level - c.value,
      kind: "cost",
    });
    level -= c.value;
  }
  rows.push({
    label: r.profit >= 0 ? "Utilidad estimada" : "Pérdida estimada",
    value: r.profit,
    start: 0,
    end: r.profit,
    kind: "profit",
  });
  return rows;
}
/** Restrict price matches by physical product; unprocessed cane/rice are not panela/milled rice. */
export function comparableProduct(crop: string, product: string) {
  const c = fold(crop),
    p = fold(product);
  if (["arroz", "cana", "cana panelera"].includes(c)) return false;
  if (c === "frijol") return p.startsWith("frijol") && !/verde|enlatad/.test(p);
  if (c === "maiz")
    return (
      p.startsWith("maiz") && /cascara|seco/.test(p) && !p.includes("trillado")
    );
  if (c === "arveja") return p.startsWith("arveja") && /seca/.test(p);
  if (c === "cebolla de rama") return p.includes("cebolla junca");
  if (c === "cebolla de bulbo") return p.includes("cebolla cabezona");
  return p === c || p.startsWith(c + " ");
}
