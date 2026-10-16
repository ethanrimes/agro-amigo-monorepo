import { expect, test } from "@playwright/test";

const markets = Array.from({ length: 14 }, (_, index) => ({
  id: `fixture-market-${index + 1}`,
  name: `Plaza ${String(index + 1).padStart(2, "0")}`,
  city: `Ciudad ${index + 1}`,
  region: index === 13 ? "Nariño" : "Cundinamarca",
  price: 14_000 - index * 100,
  min_price: 13_900 - index * 100,
  max_price: 14_100 - index * 100,
  date: "2026-09-25",
  unit: "kg",
  presentation: "Caja",
  units: "2.5 Kilogramo",
  series: "city",
  product_id: "fixture-ahuyama",
  document_id: String(index + 1).padStart(64, "0"),
  source_locator: `PDF page ${index + 1},row ${index + 1}`,
  source_page: index + 1,
}));

test("market drilldown keeps six ranked rows and exposes one exact distant source", async ({ page }) => {
  await page.route("**/api/products/fixture-ahuyama?**", (route) => route.fulfill({ json: {
    product: { id: "fixture-ahuyama", name: "Ahuyama", category: "Hortalizas", image_key: "produce" },
    markets,
    history: [{ date: "2026-09-25", price: 13_350, market_count: markets.length }],
    current: { date: "2026-09-25", price: 13_350, market_count: markets.length },
    classification: [["Hortalizas"]],
    filters: { region: "", series: "city", market: "", presentation: "Caja", units: "2.5 Kilogramo", history: "recent" },
    options: { series: ["city"], presentations: ["Caja"], units: ["2.5 Kilogramo"], markets: markets.map(({ id, name }) => ({ id, name })) },
  } }));
  await page.goto("/product/fixture-ahuyama?series=city&presentation=Caja&units=2.5+Kilogramo");

  const section = page.locator(".market-section");
  const choice = section.getByRole("group", { name: "Consultar un mercado de la comparación" });
  const search = choice.getByRole("combobox");
  await expect(section.locator(".market-row")).toHaveCount(6);
  await expect(section.locator(".market-number").first()).toHaveText("1");
  await expect(section.locator(".market-row").last()).toContainText("Plaza 06");
  await expect(section.getByRole("button", { name: /Ver los 14 mercados/ })).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);

  await search.fill("plaza 14");
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await expect(section.locator(".market-row")).toHaveCount(6);
  await expect(choice.getByRole("option", { name: /Plaza 14.*Nariño/ })).toBeVisible();
  await choice.getByRole("option", { name: /Plaza 14.*Nariño/ }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-14");
  await expect(section.locator(".market-row")).toHaveCount(7);
  const selected = section.locator(".market-row").filter({ hasText: "Plaza 14" });
  await expect(selected.locator(".market-number")).toHaveText("14");
  await expect(selected).toContainText("12.700");
  await expect(selected).toContainText("Rango: $ 12.600–$ 12.800");
  await expect(selected).toContainText("Caja · 2.5 Kilogramo");
  await expect(selected.getByRole("link", { name: "Ver fuente" })).toHaveAttribute(
    "href", /\/evidence\/0{62}14\?.*page=14.*market=fixture-market-14/,
  );
  await search.fill("zzZ");
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-14");
  await expect(section.locator(".market-row")).toHaveCount(7);
  await expect(selected.getByRole("link", { name: "Ver fuente" })).toHaveAttribute("href", /\/evidence\/0{62}14\?/);
  await search.fill("plaza 01");
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-14");
  await expect(section.locator(".market-row")).toHaveCount(7);
  await choice.getByRole("option", { name: /Plaza 01.*Cundinamarca/ }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-1");
  await expect(section.locator(".market-row")).toHaveCount(6);
  await expect(section.locator(".market-row").filter({ hasText: "Plaza 14" })).toHaveCount(0);
  await search.fill("plaza 14");
  await choice.getByRole("option", { name: /Plaza 14.*Nariño/ }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-14");
  await expect(section.locator(".market-row")).toHaveCount(7);

  await section.getByRole("combobox", { name: "Ordenar" }).selectOption("low");
  await expect(choice).toHaveAttribute("data-selected-value", "fixture-market-14");
  await expect(section.locator(".market-row")).toHaveCount(6);
  await expect(section.locator(".market-row").first()).toContainText("Plaza 14");
  await expect(section.locator(".market-number").first()).toHaveText("1");
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "");
  await section.getByRole("combobox", { name: "Ordenar" }).selectOption("high");
  await expect(section.locator(".market-row")).toHaveCount(6);
  await expect(section.locator(".market-row").filter({ hasText: "Plaza 14" })).toHaveCount(0);
});

test("empty city comparison does not invent a monthly kilogram basis", async ({ page }) => {
  await page.route("**/api/products/fixture-ahuyama?**", (route) => route.fulfill({ json: {
    product: { id: "fixture-ahuyama", name: "Ahuyama", category: "Hortalizas", image_key: "produce" },
    markets: [],
    history: [],
    current: null,
    classification: [["Hortalizas"]],
    filters: { region: "Sucre", series: "city", market: "", presentation: "Kilogramo", units: "1 Kilogramo", history: "recent" },
    options: { series: ["city"], presentations: ["Kilogramo"], units: ["1 Kilogramo"], markets: [] },
  } }));
  await page.goto("/product/fixture-ahuyama?region=Sucre&series=city&presentation=Kilogramo&units=1+Kilogramo");

  const section = page.locator(".market-section");
  await expect(section.getByText("Sin cotizaciones para los filtros aplicados.")).toBeVisible();
  await expect(section.locator(".market-row")).toHaveCount(0);
  await expect(section.locator(".market-sort")).toHaveCount(0);
  await expect(section).not.toContainText("Promedio mayorista");
  await expect(section).not.toContainText("COP por kg");
  await expect(page.getByRole("combobox", { name: "Tipo de precio" })).toHaveValue("city");
  await expect(page.getByRole("group", { name: "Unidades" })).toHaveAttribute("data-selected-value", "1 Kilogramo");
});
