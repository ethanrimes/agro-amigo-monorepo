import { expect, test } from "@playwright/test";

const quotes = Array.from({ length: 14 }, (_, index) => ({
  id: `fixture-product-${index + 1}`,
  name: `Producto ${String(index + 1).padStart(2, "0")}`,
  category: "Hortalizas",
  category_path: ["Hortalizas", "Frutos"],
  presentation: index === 13 ? "Canastilla" : "Caja",
  units: index === 13 ? "12.5 Kilogramo" : "2.5 Kilogramo",
  unit: "kg",
  series: "city",
  location_id: "fixture-market",
  location_name: "Mercado de prueba",
  price: 14_000 - index * 100,
  date: "2026-09-25",
  document_id: String(index + 1).padStart(64, "0"),
  source_locator: `PDF page ${index + 1},table 1,row ${index + 1}`,
  source_page: index + 1,
}));

const comparison = {
  kind: "markets",
  filters: { a: "fixture-market", b: "fixture-other", series: "city", scope: "market", history: "recent", dates: "latest", product: "" },
  locations: [
    { id: "fixture-market", name: "Mercado de prueba", series: ["city"] },
    { id: "fixture-other", name: "Otro mercado", series: ["city"] },
  ],
  series: ["city"],
  a_name: "Mercado de prueba",
  b_name: "Otro mercado",
  rows: quotes.map((a, index) => ({
    key: `commercial-${index + 1}`,
    a,
    b: { price: a.price + 100, date_from: a.date, date_to: a.date, location_count: 1, sources: [{ ...a, location_id: "fixture-other", location_name: "Otro mercado" }] },
    difference: 100,
    percent: 14 - index,
  })),
  matched: 14,
  unmatched: 0,
  percent: 7.5,
  summaries: [{ category: "Hortalizas", subcategory: null, count: 14, percent: 7.5 }],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/compare/markets?**", (route) => route.fulfill({ json: comparison }));
});

test("market detail keeps six ranked quotes plus one exact distant source", async ({ page }) => {
  await page.route("**/api/explore/market?**", (route) => route.fulfill({ json: {
    market: {
      id: "fixture-market", name: "Mercado de prueba", city: "Bogotá", region: "Bogotá D.C.",
      municipality_id: null, latitude: null, longitude: null, department_id: null,
      product_count: 14, date: "2026-09-25", supply_date: null,
    },
    products: [],
  } }));
  await page.goto("/market/fixture-market");
  const section = page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "Precios en este mercado", exact: true }) });
  const choice = section.getByRole("group", { name: "Consultar una cotización de este mercado" });
  const search = choice.getByRole("combobox");
  await expect(section.getByRole("article")).toHaveCount(6);
  await expect(section.getByRole("article").first()).toContainText("Producto 01");
  await expect(section.getByRole("button", { name: "Expandir lista completa" })).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("producto 14");
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await expect(section.getByRole("article")).toHaveCount(6);
  await choice.getByRole("option", { name: /Producto 14.*Canastilla.*12.5 Kilogramo/ }).click();
  await expect(section.getByRole("article")).toHaveCount(7);
  const last = section.getByRole("article").filter({ hasText: "Producto 14" });
  await expect(last).toContainText("12.700");
  await expect(last).toContainText("Canastilla · 12.5 Kilogramo");
  await expect(last.getByRole("link", { name: "Consultar fuente" })).toHaveAttribute("href", /\/evidence\/0{62}14\?.*page=14.*market=fixture-market/);
  await search.fill("zz-no-match");
  await expect(section.getByRole("article")).toHaveCount(7);
  await expect(last.getByRole("link", { name: "Consultar fuente" })).toHaveAttribute("href", /\/evidence\/0{62}14\?/);
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(section.getByRole("article")).toHaveCount(6);
  await expect(last).toHaveCount(0);
});

test("comparison preserves all summary arithmetic while limiting quote choices", async ({ page }) => {
  await page.goto("/compare/markets?a=fixture-market&b=fixture-other&series=city");
  const result = page.getByRole("region", { name: "Resultado de la comparación" });
  await expect(result).toContainText("14 combinaciones comparables");
  const section = page.locator("section.panel").filter({ has: page.getByRole("heading", { name: "Producto por producto", exact: true }) });
  const choice = section.getByRole("group", { name: "Consultar una combinación de la comparación" });
  const search = choice.getByRole("combobox");
  await expect(section.getByRole("article")).toHaveCount(6);
  await expect(section.getByRole("button", { name: "Expandir lista completa" })).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("producto 14");
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await expect(section.getByRole("article")).toHaveCount(6);
  await choice.getByRole("option", { name: /Producto 14.*Canastilla.*12.5 Kilogramo/ }).click();
  await expect(section.getByRole("article")).toHaveCount(7);
  const last = section.getByRole("article").filter({ hasText: "Producto 14" });
  await expect(last).toContainText("12.700");
  await expect(last).toContainText("Canastilla · 12.5 Kilogramo");
  await expect(last.getByRole("link", { name: "Consultar fuente" }).first()).toHaveAttribute("href", /\/evidence\/0{62}14\?.*page=14.*market=fixture-market/);
  await search.fill("no-such-product");
  await expect(section.getByRole("article")).toHaveCount(7);
  await expect(result).toContainText("14 combinaciones comparables");
  await section.getByRole("combobox", { name: "Orden" }).selectOption("name");
  await expect(section.getByRole("article")).toHaveCount(7);
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(section.getByRole("article")).toHaveCount(6);
  await expect(last).toHaveCount(0);
});
