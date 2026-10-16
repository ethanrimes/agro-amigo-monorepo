import { expect, test } from "@playwright/test";

test("a single city observation remains visible on the chart and links its own package source", async ({ page }) => {
  const original = "a".repeat(64);
  const point = { date: "2021-09-01", price: 92000, market_count: 1, sources: [{
    document_id: original, source_locator: "PDF page 1, row 1, round 1", source_page: 1,
    market_id: "fixture-market", market_name: "Barranquilla, Granabastos", source_units: "10 Kilogramo",
  }] };
  await page.route("**/api/products/fixture-single?**", (route) => route.fulfill({ json: {
    product: { id: "fixture-single", name: "Ajo importado", category: "Verduras", image_key: "produce" },
    markets: [], classification: [["Verduras"]], additional_references: [], history: [point], current: point,
    filters: { series: "city", presentation: "Caja de cartón", units: "10 Kilogramo", history: "all" },
    options: { series: ["city"], presentations: ["Caja de cartón"], units: ["10 Kilogramo"], markets: [] },
  } }));
  await page.goto("/product/fixture-single?history=all");
  const chart = page.locator(".chart-panel").first();
  await expect(chart.getByText(/Una observación.*1 de septiembre de 2021.*92\.000.*10 Kilogramo/)).toBeVisible();
  const dot = chart.locator("svg circle");
  await expect(dot).toHaveCount(1);
  await expect(dot).toHaveAttribute("fill", "#3c6748");
  await expect(dot).toHaveAttribute("cx", "422.5");
  await expect(chart.locator("svg path[fill^='url']")).toHaveCount(0);
  await dot.click();
  await expect(chart.locator(".chart-header")).toContainText("92.000");
  await chart.getByText("Ver datos en tabla", { exact: true }).click();
  const row = chart.locator("tbody tr");
  await expect(row).toHaveCount(1);
  await expect(row).toContainText("92.000");
  const source = new URL((await row.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href"))!, "http://fixture.invalid");
  expect(source.pathname).toBe(`/evidence/${original}`);
  expect(Object.fromEntries(source.searchParams)).toMatchObject({ month: point.date, page: "1", market: "fixture-market", units: "10 Kilogramo" });
});

test("a long history table remains price descending and reaches an old exact date and original", async ({ page }) => {
  const dates = Array.from({ length: 36 }, (_, index) => `${2020 + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}-28`);
  const original = "a".repeat(64);
  const history = dates.map((date, index) => ({ date, price: 1000 + index * 100, sources: [{ document_id: original, source_locator: `PDF page ${index + 1},row 12`, source_page: index + 1, market_id: "fixture-market", market_name: "Plaza de prueba" }] }));
  await page.route("**/api/products/fixture-history?**", (route) => route.fulfill({ json: { product: { id: "fixture-history", name: "Ahuyama", category: "Hortalizas", image_key: "produce" }, markets: [], classification: [["Hortalizas"]], additional_references: [], history, current: { date: dates[35], price: 4500, market_count: 1 }, filters: { history: "all" }, options: { series: [], presentations: [], units: [], markets: [] } } }));
  await page.goto("/product/fixture-history?history=all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const table = page.locator(".chart-data table");
  await expect(table.locator("tbody tr")).toHaveCount(12);
  await expect(table.locator("tbody tr").first()).toContainText("4.500");
  await expect(table.locator("tbody tr").last()).toContainText("3.400");
  const choice = page.getByRole("group", { name: "Consultar una fecha de esta tabla", exact: true });
  const search = choice.getByRole("combobox");
  const selectedSource = choice.getByRole("link", { name: "Consultar fuente de la fecha seleccionada", exact: true });
  await expect(selectedSource).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("enero 2020");
  await expect(choice.getByRole("option", { name: /28 de enero de 2020/ })).toBeVisible();
  await search.fill("2020 enero");
  await expect(choice.getByRole("option", { name: /28 de enero de 2020/ })).toBeVisible();
  await search.fill(dates[0]);
  await expect(table.locator("tbody tr")).toHaveCount(12);
  await choice.getByRole("option", { name: /28 de enero de 2020/ }).click();
  await expect(selectedSource).toBeVisible();
  await expect(selectedSource).toHaveAttribute("href", /page=1.*month=2020-01-28/);
  await expect(table.locator("tbody tr")).toHaveCount(13);
  const row = table.getByRole("row").filter({ hasText: "28 de enero de 2020" });
  await expect(row).toContainText("1.000");
  await expect(row.getByRole("link", { name: "Consultar fuente", exact: true })).toHaveAttribute("href", /page=1.*month=2020-01-28/);
  await search.fill("no-such-date-zzzz");
  await expect(selectedSource).toHaveAttribute("href", /page=1.*month=2020-01-28/);
  await expect(row).toBeVisible();
  await search.press("Escape");
  await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(table.locator("tbody tr")).toHaveCount(12);
  await expect(selectedSource).toHaveCount(0);
});

test("a long official-reference table searches the native date, unit and own original while retaining ordering", async ({ page }) => {
  const dates = Array.from({ length: 36 }, (_, index) => `${2020 + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}-28`);
  const history = dates.map((observed_on, index) => ({ id: "fixture-reference", product_name: "Leche cruda", category: "Leche", publisher: "DANE", details: {}, market: "Costa Caribe", department: "", basis: "Precio mensual", price: 1000 + index * 100, currency: "COP", unit: "litro", observed_on, document_id: String(index + 1).padStart(64, "0"), source_page: index + 1, source_locator: `PDF page ${index + 1},row 12` }));
  await page.route("**/api/references?id=fixture-reference", (route) => route.fulfill({ json: { reference: history[35], history } }));
  await page.goto("/references/fixture-reference");
  await page.getByRole("combobox", { name: "Historial de precios", exact: true }).selectOption("all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const table = page.locator(".reference-history-table");
  await expect(table.locator("tbody tr")).toHaveCount(12);
  const choice = page.getByRole("group", { name: "Consultar un registro de esta tabla", exact: true });
  const search = choice.getByRole("combobox");
  const selectedSource = choice.getByRole("link", { name: "Consultar fuente del registro seleccionado", exact: true });
  await expect(selectedSource).toHaveCount(0);
  await search.fill("enero 2020");
  await expect(choice.getByRole("option", { name: /28 de enero de 2020/ })).toBeVisible();
  await search.fill(dates[0]);
  await choice.getByRole("option", { name: /28 de enero de 2020/ }).click();
  await expect(choice).toContainText("COP / litro");
  await expect(selectedSource).toBeVisible();
  const selectedUrl = new URL((await selectedSource.getAttribute("href"))!, "http://fixture.invalid");
  expect(selectedUrl.pathname).toBe(`/evidence/${history[0].document_id}`);
  expect(Object.fromEntries(selectedUrl.searchParams)).toMatchObject({ page: "1", month: dates[0], units: "litro", currency: "COP", marketName: "Costa Caribe", productName: "Leche cruda" });
  await expect(table.locator("tbody tr")).toHaveCount(13);
  const row = table.getByRole("row").filter({ hasText: "28 de enero de 2020" });
  await expect(row.getByRole("link", { name: "Consultar", exact: true })).toHaveAttribute("href", /page=1.*month=2020-01-28/);
  await page.getByRole("combobox", { name: "Orden", exact: true }).selectOption("date");
  await expect(table.locator("tbody tr").first()).toContainText("28 de diciembre de 2022");
  await expect(row).toBeVisible();
  await search.fill("no-such-date-zzzz");
  await expect(row).toBeVisible();
  await expect(selectedSource).toHaveAttribute("href", selectedUrl.pathname + selectedUrl.search);
  await search.press("Escape");
  await page.getByRole("combobox", { name: "Historial de precios", exact: true }).selectOption("recent");
  await expect(selectedSource).toHaveCount(0);
});

test("an old selected date exposes every own market source, folds accents and preserves its exact selection", async ({ page }) => {
  const dates = Array.from({ length: 36 }, (_, index) => `${2020 + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}-28`);
  const markets = ["Bogotá, D.C., Corabastos", ...Array.from({ length: 8 }, (_, index) => `Mercado ${index + 1}`)];
  const sources = markets.map((market_name, index) => ({ document_id: String(index + 1).padStart(64, "0"), source_locator: `PDF page ${index + 1},row 12`, source_page: index + 1, market_id: `market-${index}`, market_name }));
  const history = dates.map((date, index) => ({ date, price: 1000 + index * 100, sources: index === 0 ? sources : [] }));
  await page.route("**/api/products/fixture-history?**", (route) => route.fulfill({ json: { product: { id: "fixture-history", name: "Ahuyama", category: "Hortalizas", image_key: "produce" }, markets: [], classification: [["Hortalizas"]], additional_references: [], history, current: { date: dates[35], price: 4500, market_count: 1 }, filters: { history: "all" }, options: { series: [], presentations: [], units: [], markets: [] } } }));
  await page.goto("/product/fixture-history?history=all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const choice = page.getByRole("group", { name: "Consultar una fecha de esta tabla", exact: true });
  await choice.getByRole("combobox").fill(dates[0]);
  await choice.getByRole("option", { name: /28 de enero de 2020/ }).click();
  await choice.getByText("Consultar 9 fuentes", { exact: true }).click();
  const sourceChoice = choice.getByRole("group", { name: "Consultar una fuente de la fecha", exact: true });
  const sourceSearch = sourceChoice.getByRole("combobox");
  const sourceLink = choice.getByRole("link", { name: "Fuente 1 · Bogotá, D.C., Corabastos", exact: true });
  for (const query of ["BOGOTA", "bogotá", "BOGOTA\u0301"]) {
    await sourceSearch.fill(query);
    await expect(sourceChoice.getByRole("option")).toHaveCount(1);
    await expect(sourceChoice.getByRole("option", { name: /Bogotá, D.C., Corabastos/ })).toBeVisible();
  }
  await sourceChoice.getByRole("option", { name: /Bogotá, D.C., Corabastos/ }).click();
  await expect(sourceLink).toBeVisible();
  const ownUrl = new URL((await sourceLink.getAttribute("href"))!, "http://fixture.invalid");
  expect(ownUrl.pathname).toBe(`/evidence/${sources[0].document_id}`);
  expect(Object.fromEntries(ownUrl.searchParams)).toMatchObject({ page: "1", month: dates[0], market: "market-0", marketName: markets[0] });
  await sourceSearch.fill("MERCADO 8");
  // The search also covers the original's page locator: mercado 7 is on page 8.
  await expect(sourceChoice.getByRole("option")).toHaveCount(2);
  await expect(sourceChoice.getByRole("option", { name: /^Mercado 8 / })).toBeVisible();
  await expect(sourceLink).toHaveAttribute("href", ownUrl.pathname + ownUrl.search);
  await sourceSearch.press("Escape");
  await sourceChoice.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(sourceLink).toHaveCount(0);
  await choice.getByRole("combobox", { name: "Consultar una fecha de esta tabla", exact: true }).fill(dates[1]);
  await choice.getByRole("option", { name: /28 de febrero de 2020/ }).click();
  await expect(choice.getByRole("link")).toHaveCount(0);
  await expect(choice.getByText("Consultar 9 fuentes", { exact: true })).toHaveCount(0);
});
