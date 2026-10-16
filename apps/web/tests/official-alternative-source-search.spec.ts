import { expect, test } from "@playwright/test";

const alternatives = Array.from({ length: 14 }, (_, index) => ({
  quote_key: `fixture-quote-${index + 1}`,
  product_id: "fixture-aceite",
  product_name: "Aceite vegetal mezcla",
  category: "Aceites",
  publisher: index === 13 ? "Editor USD independiente" : "DANE · SIPSA",
  series: "monthly",
  basis: index === 13 ? "Precio ex-dock" : "Precio mayorista",
  currency: index === 13 ? "USD" : "COP",
  unit: index === 13 ? "galón" : "litro",
  market: `Mercado ${String(index + 1).padStart(2, "0")}`,
  observed_on: index === 13 ? "2025-01-31" : "2026-08-31",
  period_start: null,
  price: index === 13 ? 12.3456 : 10_000 + index,
  min_price: null,
  max_price: null,
  document_id: String(index + 1).padStart(64, "0"),
  source_locator: `PDF page ${index + 1}`,
  source_url: "https://example.invalid/original.pdf",
  details: {},
}));

function productResponse(rows: typeof alternatives) {
  return {
    product: { id: "fixture-aceite", name: "Aceite vegetal mezcla", category: "Aceites", image_key: "produce" },
    markets: [],
    history: [{ date: "2026-08-31", price: 10_000, market_count: 1 }],
    current: { date: "2026-08-31", price: 10_000, market_count: 1 },
    classification: [["Aceites"]],
    additional_references: rows,
    filters: { region: "", series: "monthly", market: "", presentation: "Litro", units: "1 litro", history: "recent" },
    options: { series: ["monthly"], presentations: ["Litro"], units: ["1 litro"], markets: [] },
  };
}

test("many alternative originals require exact choice and retain their own money, unit, and route", async ({ page }) => {
  await page.route("**/api/products/fixture-aceite?**", (route) => route.fulfill({ json: productResponse(alternatives) }));
  await page.goto("/product/fixture-aceite?series=monthly&presentation=Litro&units=1+litro");
  const disclosure = page.getByText("Más precios y fuentes disponibles (14)", { exact: true });
  await disclosure.click();
  const list = page.locator(".entity-price-list");
  const choice = page.getByRole("group", { name: "Consultar otra referencia y fuente" });
  const search = choice.getByRole("combobox");
  await expect(list.locator("article")).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("mercado 14");
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await expect(list.locator("article")).toHaveCount(0);
  const lastOption = choice.getByRole("option", { name: /Mercado 14.*Editor USD independiente.*Precio ex-dock.*2025.*USD.*galón/ });
  await expect(lastOption).toBeVisible();
  await lastOption.click();
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-quote-14");
  await expect(list.locator("article")).toHaveCount(1);
  await expect(list.locator("article")).toContainText("Editor USD independiente");
  await expect(list.locator("article")).toContainText("Precio ex-dock");
  await expect(list.locator("article")).toContainText("2025");
  await expect(list.locator("article")).toContainText("USD");
  await expect(list.locator("article")).toContainText("12,3456");
  await expect(list.locator("article")).toContainText("Por galón");
  await expect(list.getByRole("link", { name: "Ver precio y fuente" })).toHaveAttribute("href", "/references/fixture-quote-14");

  await search.fill("mercado 01");
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-quote-14");
  await expect(list.locator("article")).toHaveCount(1);
  await expect(list.getByRole("link", { name: "Ver precio y fuente" })).toHaveAttribute("href", "/references/fixture-quote-14");
  await choice.getByRole("option", { name: /Mercado 01.*DANE/ }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-quote-1");
  await expect(list.locator("article")).toHaveCount(1);
  await expect(list.getByRole("link", { name: "Ver precio y fuente" })).toHaveAttribute("href", "/references/fixture-quote-1");
  await expect(list.locator("article")).toContainText("COP");
  await expect(list.locator("article")).toContainText("Por litro");
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await expect(list.locator("article")).toHaveCount(0);
});

test("six or fewer alternatives keep their separate original cards", async ({ page }) => {
  await page.route("**/api/products/fixture-aceite?**", (route) => route.fulfill({ json: productResponse(alternatives.slice(0, 4)) }));
  await page.goto("/product/fixture-aceite?series=monthly&presentation=Litro&units=1+litro");
  await page.getByText("Más precios y fuentes disponibles (4)", { exact: true }).click();
  await expect(page.getByRole("group", { name: "Consultar otra referencia y fuente" })).toHaveCount(0);
  const cards = page.locator(".entity-price-list article");
  await expect(cards).toHaveCount(4);
  await expect(cards.nth(3).getByRole("link", { name: "Ver precio y fuente" })).toHaveAttribute("href", "/references/fixture-quote-4");
});
