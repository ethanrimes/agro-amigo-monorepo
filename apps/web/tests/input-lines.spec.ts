import { expect, test } from "@playwright/test";

const documentId = "c3556910021fc440ff4b532b8c5ba185ffd71aed098d0f6f76d009d1f0aa4e38";
// Independent source oracle: department history, sheet3.2, January2023,
// Antioquia. Same name/brand/roll length has two different commercial lines.
const lines = [
  [200, "Finquero", 70, 152970.5], [200, "Iowa", 71, 147122.2222222],
  [350, "Finquero", 91, 262487.5555556], [350, "Iowa", 92, 251116.6666667],
  [500, "Finquero", 113, 369795.4545455], [500, "Iowa", 115, 351075],
] as const;

for (const [metres, line, row, price] of lines) test(`wire ${metres}m ${line}: separate price history and exact source`, async ({ page, request }) => {
  const id = `alambre-de-puas-nro-14-rollo-por-${metres}-metros-proalco-bekaert-linea-${line.toLowerCase()}`;
  const query = new URLSearchParams({ id, department: "Antioquia", scope: "department", history: "all" });
  const response = await request.get(`/api/explore/input?${query}`);
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.input.product_line).toBe(line);
  expect(data.input.presentation).toBe(`rollo por ${metres} metros`);
  const point = data.history.find((point: any) => point.date === "2023-01-31");
  expect(point.price).toBeCloseTo(price, 7);
  expect(point.sources).toEqual([{
    document_id: documentId, source_locator: `3.2!row ${row}; full product identity`,
    source_page: null, market_id: "Antioquia", market_name: "Antioquia",
  }]);
  await page.goto(`/insumo/${id}?department=Antioquia&history=all`);
  // The read-only map has its own filter summary outside the main content.
  // Check the price history's selection, including the commercial line.
  await expect(page.locator("#main-content").getByLabel("Filtros aplicados")).toContainText(line);
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const historical = page.locator(".chart-data tbody tr").filter({ hasText: "31 de enero de 2023" });
  await expect(historical).toHaveCount(1);
  await expect(historical.locator("a.evidence-link")).toHaveAttribute("href", new RegExp(documentId));
  const source = new URL((await historical.locator("a.evidence-link").getAttribute("href"))!, "http://localhost");
  expect(source.searchParams.get("locator")).toBe(`3.2!row ${row}; full product identity`);
  expect(source.searchParams.get("sheet")).toBe("3.2");
  expect(source.searchParams.get("row")).toBe(String(row));
  await page.screenshot({ path: test.info().outputPath(`wire-${metres}-${line}.png`), fullPage: true });
});
