import { expect, test } from "@playwright/test";

const day = "2026-09-25";
const sourceId = (index: number) => index.toString(16).padStart(64, "0");
const historySources = (count: number) => Array.from({ length: count }, (_, index) => ({
  document_id: sourceId(index + 1),
  source_locator: `PDF page ${index + 1}, row ${index + 1}`,
  source_page: index + 1,
  market_id: `market-${index + 1}`,
  market_name: `Plaza ${String(index + 1).padStart(2, "0")}`,
}));

test("product history keeps a short source list and makes a long list an exact held choice", async ({ page }) => {
  await page.route("**/api/products/fixture-sources-**", (route) => {
    const count = new URL(route.request().url()).pathname.includes("fixture-sources-6") ? 6 : 10;
    route.fulfill({ json: {
      product: { id: `fixture-sources-${count}`, name: "Mora de castilla", category: "Frutas", image_key: "produce" },
      markets: [], classification: [["Frutas"]], additional_references: [],
      current: { date: day, price: 20_500, market_count: count },
      history: [{ date: day, price: 20_500, sources: historySources(count) }],
      filters: { region: "", series: "city", market: "", presentation: "Caja", units: "2.5 Kilogramo", history: "all" },
      options: { series: ["city"], markets: [], presentations: ["Caja"], units: ["2.5 Kilogramo"] },
    } });
  });

  await page.goto("/product/fixture-sources-6?series=city&presentation=Caja&units=2.5+Kilogramo&history=all");
  await page.locator(".chart-data > summary").click();
  const short = page.locator(".chart-data details.history-row-source");
  await short.locator("summary").click();
  await expect(short.locator("li a.evidence-link")).toHaveCount(6);
  await expect(short.getByRole("group", { name: "Consultar una fuente de la fecha" })).toHaveCount(0);

  await page.goto("/product/fixture-sources-10?series=city&presentation=Caja&units=2.5+Kilogramo&history=all");
  await page.locator(".chart-data > summary").click();
  const long = page.locator(".chart-data details.history-row-source").first();
  await long.locator("summary").click();
  const choice = long.getByRole("group", { name: "Consultar una fuente de la fecha" });
  const search = choice.getByRole("combobox");
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("plaza 10");
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
  await choice.getByRole("option", { name: /Plaza 10.*25 de septiembre de 2026.*2.5 Kilogramo/ }).click();
  await expect(choice).toContainText("Plaza 10");
  await expect(choice).toContainText("25 de septiembre de 2026");
  await expect(choice).toContainText("2.5 Kilogramo");
  const link = long.locator("a.evidence-link");
  await expect(link).toHaveCount(1);
  let href = new URL((await link.getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${sourceId(10)}`);
  expect(href.searchParams.get("locator")).toBe("PDF page 10, row 10");
  expect(href.searchParams.get("market")).toBe("market-10");
  expect(href.searchParams.get("month")).toBe(day);
  await search.fill("no-such-market");
  await expect(choice.getByText("Sin coincidencias. Prueba otro nombre.")).toBeVisible();
  await expect(link).toHaveCount(1);
  href = new URL((await link.getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${sourceId(10)}`);
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
});

const comparisonQuote = (index: number) => ({
  id: "mora", name: "Mora de castilla", category: "Frutas", category_path: ["Frutas"],
  presentation: "Caja", units: "2.5 Kilogramo", unit: "kg", series: "city",
  location_id: `market-${index}`, location_name: `Plaza ${String(index).padStart(2, "0")}`,
  price: 20_000 + index, date: day, document_id: sourceId(index),
  source_locator: `PDF page ${index}, row ${index}`, source_page: index,
});

test("comparison constituent sources show one exact location for long sets and preserve short sets", async ({ page }) => {
  await page.route("**/api/compare/markets?**", (route) => {
    const count = new URL(route.request().url()).searchParams.get("fixture") === "short" ? 6 : 10;
    const sources = Array.from({ length: count }, (_, index) => comparisonQuote(index + 1));
    route.fulfill({ json: {
      kind: "markets", filters: { a: "market-a", b: "__national__", series: "city", scope: "department", history: "all", dates: "latest", product: "" },
      locations: [{ id: "market-a", name: "Mercado A" }], series: ["city"], a_name: "Mercado A", b_name: "Promedio nacional",
      rows: [{ key: "mora", a: comparisonQuote(1), b: { price: 20_004, date_from: day, date_to: day, location_count: count, sources }, difference: 3, percent: 0.01 }],
      matched: 1, unmatched: 0, percent: 0.01, summaries: [],
    } });
  });
  await page.goto("/compare/markets?series=city&a=market-a&fixture=short");
  const short = page.locator("details").filter({ hasText: "Ver 6 precios y fuentes del promedio" });
  await short.locator("summary").click();
  await expect(short.locator("a.evidence-link")).toHaveCount(6);
  await expect(short.getByRole("group", { name: "Consultar una ubicación del promedio" })).toHaveCount(0);

  await page.goto("/compare/markets?series=city&a=market-a&fixture=long");
  const long = page.locator("details").filter({ hasText: "Ver 10 precios y fuentes del promedio" });
  await long.locator("summary").click();
  const choice = long.getByRole("group", { name: "Consultar una ubicación del promedio" });
  const search = choice.getByRole("combobox");
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("plaza 10");
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
  await choice.getByRole("option", { name: /Plaza 10.*25 de septiembre de 2026.*2.5 Kilogramo/ }).click();
  await expect(choice).toContainText("Plaza 10");
  await expect(choice).toContainText("25 de septiembre de 2026");
  await expect(choice).toContainText("2.5 Kilogramo");
  const link = long.locator("a.evidence-link");
  await expect(link).toHaveCount(1);
  let href = new URL((await link.getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${sourceId(10)}`);
  expect(href.searchParams.get("locator")).toBe("PDF page 10, row 10");
  expect(href.searchParams.get("market")).toBe("market-10");
  await search.fill("no-such-market");
  await expect(choice.getByText("Sin coincidencias. Prueba otro nombre.")).toBeVisible();
  await expect(link).toHaveCount(1);
  href = new URL((await link.getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${sourceId(10)}`);
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(long.locator("a.evidence-link")).toHaveCount(0);
});
