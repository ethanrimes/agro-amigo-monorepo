import { test, expect, type Page, type Response } from "@playwright/test";
import type { SupplyData } from "../src/lib/explore-types";

const market = "sipsa-armenia-mercar";
const tonnes = (kg: number) =>
  new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(
    kg / 1000,
  );
const monthLabel = (month: string) =>
  new Date(`${month}T12:00:00Z`).toLocaleDateString("es-CO", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bogota",
  });
const supplyResponse = (page: Page, month = "") =>
  page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname === "/api/explore/supply" &&
      url.searchParams.get("market") === market &&
      url.searchParams.get("month") === month
    );
  });
async function readSupply(response: Response): Promise<SupplyData> {
  expect(response.ok()).toBeTruthy();
  expect(new URL(response.url()).searchParams.get("history")).toBe("all");
  return response.json();
}

test("one month selector reaches all retained 2019/2020 supply with matching totals, records and sources", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(240_000);
  if (testInfo.project.name === "mobile") {
    await page.setViewportSize({ width: 320, height: 844 });
  }
  await page.goto(`/market/${market}`);
  const initialResponse = supplyResponse(page);
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  const initial = await readSupply(await initialResponse);
  const controls = page.getByRole("region", {
    name: "Filtros de abastecimiento",
  });
  await expect(controls.getByRole("combobox")).toHaveCount(1);
  await expect(
    page.getByRole("combobox", { name: "Historial de abastecimiento" }),
  ).toHaveCount(0);
  const month = page.getByRole("combobox", { name: "Mes de consulta" });
  await expect(month).toBeEnabled();
  const months = await month
    .locator("option")
    .evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    );
  expect(months).toEqual(initial.history.map((entry) => entry.date).reverse());
  await expect(month).toHaveValue(initial.selected_period!);
  const historicalMonths = [2019, 2020].flatMap((year) =>
    Array.from(
      { length: 12 },
      (_, index) => `${year}-${String(index + 1).padStart(2, "0")}-01`,
    ),
  );
  expect(months).toEqual(expect.arrayContaining(historicalMonths));
  const validated: object[] = [];

  for (const selected of historicalMonths) {
    const response = supplyResponse(page, selected);
    await month.selectOption(selected);
    const body = await readSupply(await response);
    expect(body.selected_period).toBe(selected);
    expect(body.rows.length).toBeGreaterThan(0);
    await expect(month).toBeEnabled();
    await expect(month).toHaveValue(selected);
    await expect(page.locator(".supply-summary")).toBeVisible();
    const kg = body.rows.reduce((sum, row) => sum + row.quantity_kg, 0);
    expect(kg).toBeCloseTo(
      body.history.find((entry) => entry.date === selected)!.quantity_kg,
      2,
    );
    await expect(page.locator(".supply-summary h2")).toHaveText(
      `${tonnes(kg)} toneladas`,
    );
    const applied = page.locator(".supply-content > .applied-filters");
    await expect(applied).toContainText(`Mes: ${monthLabel(selected)}`);
    await expect(applied).toContainText("Llegadas reportadas · DANE SIPSA-A");
    await expect(applied).not.toContainText(/Últimos 12 meses|Completo/);
    await expect(
      page.locator('.supply-bars button[aria-pressed="true"]'),
    ).toHaveAccessibleName(`${monthLabel(selected)}: ${tonnes(kg)} toneladas`);

    // Compare every displayed product row with the response to the UI's own request.
    const displayed = await page
      .locator(".supply-list > article")
      .evaluateAll((articles) =>
        articles.map((article) => ({
          name: article.querySelector(
            "div:first-child > a, div:first-child > strong",
          )?.textContent,
          quantity: article.querySelector("div:last-child > strong")
            ?.textContent,
          source: article.querySelector(".evidence-link")?.getAttribute("href"),
        })),
      );
    expect(displayed).toHaveLength(body.rows.length);
    for (const [index, row] of body.rows.entries()) {
      expect(row.period_start).toBe(selected);
      expect(displayed[index].name).toBe(row.food_name);
      expect(displayed[index].quantity).toBe(`${tonnes(row.quantity_kg)} t`);
      const link = new URL(displayed[index].source!, "http://localhost");
      expect(decodeURIComponent(link.pathname)).toBe(
        `/evidence/${row.document_id}`,
      );
      expect(link.searchParams.get("market")).toBe(row.market_id);
      expect(link.searchParams.get("food")).toBe(row.food_id);
      expect(link.searchParams.get("month")).toBe(selected);
      expect(link.searchParams.get("product") || null).toBe(
        row.product_id || null,
      );
    }

    // Resolve a real archived-source record for every selected month, without downloading its workbook.
    const sourceResponse = await request.get(`/api${displayed[0].source}`);
    expect(sourceResponse.ok()).toBeTruthy();
    const source = await sourceResponse.json();
    const row = body.rows[0];
    expect(source.id).toBe(row.document_id);
    expect(Number(source.bytes)).toBeGreaterThan(0);
    expect(source.records).toHaveLength(1);
    expect(source.records[0]).toMatchObject({
      food_name: row.food_name,
      market_id: row.market_id,
      period_start: selected,
      first_reported_on: row.first_reported_on,
      observed_on: row.observed_on,
      reporting_days: row.reporting_days,
    });
    expect(Number(source.records[0].quantity_kg)).toBeCloseTo(
      row.quantity_kg,
      2,
    );
    expect(Object.keys(source.records[0].source_rows).length).toBeGreaterThan(
      0,
    );
    validated.push({
      month: selected,
      rows: body.rows.length,
      total_kg: kg,
      source: row.document_id,
    });
  }

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  if (testInfo.project.name === "mobile") {
    const width = await month.evaluate((element) => {
      const panel = element.closest("section")!;
      const style = getComputedStyle(panel);
      return {
        field: element.getBoundingClientRect().width,
        available:
          panel.clientWidth -
          parseFloat(style.paddingLeft) -
          parseFloat(style.paddingRight),
      };
    });
    expect(Math.abs(width.field - width.available)).toBeLessThanOrEqual(2);
  }
  await controls.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("supply-all-months.png") });
  await testInfo.attach("all-months-source-agreement", {
    body: JSON.stringify({ available_months: months, validated }, null, 2),
    contentType: "application/json",
  });
});

test("supply retries a failed selected historical month without adding a history switch", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto(`/market/${market}`);
  const initialResponse = supplyResponse(page);
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await readSupply(await initialResponse);
  const month = page.getByRole("combobox", { name: "Mes de consulta" });
  await expect(month).toBeEnabled();
  const selected = "2019-01-01";
  await page.route("**/api/explore/supply?**", (route) =>
    route.fulfill({ status: 503, json: { error: "Prueba de recuperación" } }),
  );
  await month.selectOption(selected);
  const error = page.locator("main [role=alert]");
  await expect(error).toContainText("Prueba de recuperación");
  await expect(month).toHaveValue(selected);
  await expect(
    page.getByRole("combobox", { name: "Historial de abastecimiento" }),
  ).toHaveCount(0);
  await page.unroute("**/api/explore/supply?**");
  const retryResponse = supplyResponse(page, selected);
  await error.getByRole("button").click();
  const body = await readSupply(await retryResponse);
  expect(body.selected_period).toBe(selected);
  await expect(page.locator(".supply-summary h2")).toHaveText(
    `${tonnes(body.rows.reduce((sum, row) => sum + row.quantity_kg, 0))} toneladas`,
  );
  await expect(month).toHaveValue(selected);
});
