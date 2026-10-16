import { test, expect } from "@playwright/test";

test("daily market search reaches a distant plaza while the product overview remains bounded", async ({ page }) => {
  const observations = Array.from({ length: 14 }, (_, index) => ({
    observed_on: "2016-09-05", product_name: "Habichuela", market_name: index === 13 ? "Última plaza" : `Plaza ${index + 1}`,
    price: 2500 - index * 50, unit: "kg", change_percent: index,
    document_id: "a".repeat(64), source_locator: `Boletín diario!row 12,col ${index + 2}`,
  }));
  await page.route("**/api/planning/daily-dates", (route) => route.fulfill({ json: [{ date: "2016-09-05" }] }));
  await page.route("**/api/planning/daily", (route) => route.fulfill({ json: observations }));
  await page.route("**/api/planning/daily-supply-source**", (route) => route.fulfill({ json: null }));
  await page.goto("/daily");
  const product = page.getByRole("group", { name: "Buscar producto en el boletín", exact: true });
  await product.getByRole("combobox").fill("habichuela");
  await product.getByRole("option", { name: "Habichuela", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(6);
  await expect(page.getByRole("article").first()).toContainText("2.500");
  const plaza = page.getByRole("group", { name: "Plaza del boletín", exact: true });
  const search = plaza.getByRole("combobox");
  await search.click();
  await expect(plaza.getByRole("option")).toHaveCount(8);
  await search.fill("ultima plaza");
  await expect(page.getByRole("article")).toHaveCount(6);
  await plaza.getByRole("option", { name: "Última plaza", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("article")).toContainText("1.850");
  await expect(page.getByRole("article")).toContainText("13 %");
  await expect(page.getByRole("article").getByRole("link", { name: "Comprobar este precio", exact: true })).toHaveAttribute("href", /col=15.*marketName=%C3%9Altima\+plaza.*month=2016-09-05/);
  await expect(page.getByLabel("Filtros aplicados")).toContainText("Última plaza");
  await search.fill("no-such-plaza-zzzz");
  await expect(page.getByRole("article")).toHaveCount(1);
  await search.press("Escape");
  await plaza.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(6);
});

test("daily bulletin opens an exact product without rendering the full price list", async ({ page }) => {
  const names = ["Ahuyama", "Ahuyama criolla", ...Array.from({ length: 10 }, (_, index) => `Producto ${index}`)];
  const observations = names.flatMap((name) => ["Bogotá", "Medellín"].map((market_name) => ({
    observed_on: "2012-06-27", product_name: name, market_name,
    price: name === "Ahuyama" && market_name === "Bogotá" ? 775 : 623,
    unit: "kg", change_percent: -1, document_id: "daily-fixture",
    source_page: 1, source_locator: `PDF page 1; ${name}; ${market_name}`,
  })));
  await page.route("**/api/planning/daily-dates", (route) => route.fulfill({ json: [{ date: "2012-06-27" }] }));
  await page.route("**/api/planning/daily", (route) => route.fulfill({ json: observations }));
  await page.route("**/api/planning/daily-supply-source**", (route) => route.fulfill({ json: null }));
  await page.goto("/daily");
  const selector = page.getByRole("group", { name: "Buscar producto en el boletín", exact: true });
  const search = selector.getByRole("combobox");
  await expect(page.getByText("24 referencias disponibles", { exact: true })).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
  await search.press("ArrowDown");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(8);
  await search.fill("ahuyama");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(2);
  await expect(page.getByRole("article")).toHaveCount(0);
  await page.getByRole("listbox").getByRole("option", { name: "Ahuyama", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByRole("article").getByRole("heading", { name: "Ahuyama", exact: true })).toHaveCount(2);
  await expect(page.getByRole("article").filter({ hasText: "Bogotá" })).toContainText("775");
  await search.fill("criolla");
  await expect(selector).toContainText("Seleccionado: Ahuyama");
  await expect(page.getByRole("article").getByRole("heading", { name: "Ahuyama", exact: true })).toHaveCount(2);
  await page.getByRole("listbox").getByRole("option", { name: "Ahuyama criolla", exact: true }).click();
  await expect(page.getByRole("article").getByRole("heading", { name: "Ahuyama criolla", exact: true })).toHaveCount(2);
  await selector.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(0);
  await expect(page.getByText("24 referencias disponibles", { exact: true })).toBeVisible();
});

test("suggestions remain visible above a field near the viewport bottom", async ({ page }) => {
  await page.route("**/api/planning/daily-dates", (route) => route.fulfill({ json: [{ date: "2012-06-27" }] }));
  await page.route("**/api/planning/daily", (route) => route.fulfill({ json: [{
    observed_on: "2012-06-27", product_name: "Ahuyama", market_name: "Bogotá", price: 775,
    unit: "kg", change_percent: -1, document_id: "daily-fixture", source_page: 1, source_locator: "PDF page 1",
  }] }));
  await page.route("**/api/planning/daily-supply-source**", (route) => route.fulfill({ json: null }));
  await page.goto("/daily");
  const search = page.getByRole("combobox", { name: "Buscar producto en el boletín", exact: true });
  await expect(search).toBeVisible();
  // Layout fixture for the space left by a mobile keyboard; no production data or browser preference changes.
  await page.addStyleTag({ content: '.searchable-select[aria-label="Buscar producto en el boletín"] { position: fixed; bottom: 35px; left: 40px; width: 260px; z-index: 100; background: white; }' });
  await search.fill("ahuyama");
  const list = page.getByRole("listbox", { name: "Sugerencias: Buscar producto en el boletín", exact: true });
  await expect(list).toHaveAttribute("data-placement", "above");
  const popup = await list.boundingBox();
  const field = await search.boundingBox();
  expect(popup!.y).toBeGreaterThanOrEqual(0);
  expect(popup!.y + popup!.height).toBeLessThan(field!.y);
  await list.getByRole("option", { name: "Ahuyama", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("article")).toContainText("775");
});
