import { expect, test } from "@playwright/test";

test("product history control loads older dates without losing city filters", async ({ page }) => {
  await page.setViewportSize({ width: 411, height: 845 });
  const requestedPeriods: string[] = [];
  const market = "sipsa-popayan-plaza-de-mercado-del-barrio-bolivar";
  await page.route("**/api/products/banano-criollo?**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    const period = query.get("history") || "recent";
    requestedPeriods.push(period);
    const history = [
      ...(period === "all" ? [{
        date: "2024-07-05", price: 2350, market_count: 1,
        sources: [{
          document_id: "50d273edf3673067e4901722a4e38a76f6b4b91c2a227200799f18d4a012ec49",
          source_locator: "PDF page 1,table 1,row 40,round 1", source_page: 1,
          market_id: market, market_name: "Popayán, Plaza de mercado del barrio Bolívar",
        }],
      }] : []),
      { date: "2026-09-25", price: 1800, market_count: 1 },
    ];
    await route.fulfill({ json: {
      product: { id: "banano-criollo", name: "Banano criollo", category: "Frutas", image_key: "banana" },
      markets: [{
        id: market, market_id: market, name: "Popayán, Plaza de mercado del barrio Bolívar",
        market_name: "Popayán, Plaza de mercado del barrio Bolívar", city: "Popayán", region: "Cauca",
        date: "2026-09-25", price: 1800, min_price: 1700, max_price: 1900,
        series: "city", presentation: "Kilogramo", units: "1 Kilogramo", unit: "kg",
        document_id: "a".repeat(64), source_locator: "PDF page 1", source_page: 1,
      }],
      history,
      current: history.at(-1),
      classification: [["Frutas", "Otras frutas"]],
      filters: { region: "Cauca", series: "city", market, presentation: "Kilogramo", units: "1 Kilogramo", history: period },
      options: {
        series: ["city"], presentations: ["Kilogramo"], units: ["1 Kilogramo"],
        markets: [{ id: market, name: "Popayán, Plaza de mercado del barrio Bolívar" }],
      },
    } });
  });

  await page.goto(`/product/banano-criollo?region=Cauca&series=city&market=${market}&presentation=Kilogramo&units=1+Kilogramo`);
  const period = page.getByRole("combobox", { name: "Período del historial" });
  await expect(period).toHaveValue("recent");
  await expect(page.locator(".applied-filters")).toContainText("Fechas recientes");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  await expect(page.getByText("5 de julio de 2024", { exact: true })).toHaveCount(0);

  await period.selectOption("all");
  await expect(period).toHaveValue("all");
  await expect(page.locator(".applied-filters")).toContainText("Todo el historial");
  await expect(page.locator(".applied-filters")).toContainText("Popayán, Plaza de mercado del barrio Bolívar");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const oldRow = page.locator("tr").filter({ hasText: "5 de julio de 2024" });
  await expect(oldRow).toContainText("2.350");
  await expect(oldRow.getByRole("link", { name: "Consultar fuente" })).toHaveAttribute(
    "href", /\/evidence\/50d273edf3673067e4901722a4e38a76f6b4b91c2a227200799f18d4a012ec49\?.*page=1/,
  );
  await expect(page.getByRole("group", { name: "Mercado", exact: true })).toHaveAttribute("data-selected-value", market);
  await expect(page.getByRole("group", { name: "Presentación", exact: true })).toHaveAttribute("data-selected-value", "Kilogramo");
  await expect(page.getByRole("group", { name: "Unidades", exact: true })).toHaveAttribute("data-selected-value", "1 Kilogramo");
  expect(requestedPeriods).toContain("all");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("a multi-market history point discloses each contributing source", async ({ page }) => {
  await page.setViewportSize({ width: 411, height: 845 });
  await page.route("**/api/products/banano-criollo?**", async (route) => {
    await route.fulfill({ json: {
      product: { id: "banano-criollo", name: "Banano criollo", category: "Frutas", image_key: "banana" },
      markets: [],
      history: [{
        date: "2024-07-05", price: 2450, market_count: 2,
        sources: [
          { document_id: "a".repeat(64), source_locator: "PDF page 1,row 40", source_page: 1, market_id: "popayan", market_name: "Popayán" },
          { document_id: "b".repeat(64), source_locator: "PDF page 2,row 8", source_page: 2, market_id: "cali", market_name: "Cali" },
        ],
      }],
      current: { date: "2024-07-05", price: 2450, market_count: 2 },
      classification: [["Frutas"]],
      filters: { region: "", series: "city", market: "", presentation: "Kilogramo", units: "1 Kilogramo", history: "all" },
      options: { series: ["city"], presentations: ["Kilogramo"], units: ["1 Kilogramo"], markets: [] },
    } });
  });
  await page.goto("/product/banano-criollo?series=city&presentation=Kilogramo&units=1+Kilogramo&history=all");
  await expect(page.getByRole("combobox", { name: "Período del historial" })).toHaveValue("all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const row = page.locator("tr").filter({ hasText: "5 de julio de 2024" });
  await expect(row).toContainText("2.450");
  await expect(row.locator(".history-row-source li")).toHaveCount(0);
  await expect(row.getByRole("link")).toHaveCount(0);
  await row.getByText("Consultar 2 fuentes").click();
  await expect(row.locator(".history-row-source li")).toHaveCount(2);
  await expect(row.getByRole("link", { name: "Fuente 1 · Cali" })).toHaveAttribute("href", /\/evidence\/b{64}\?.*page=2/);
  await expect(row.getByRole("link", { name: "Fuente 2 · Popayán" })).toHaveAttribute("href", /\/evidence\/a{64}\?.*page=1/);
  await row.getByText("Consultar 2 fuentes").click();
  await expect(row.locator(".history-row-source li")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
