import { expect, test } from "@playwright/test";
import fixture from "./fixtures/supply-barranquillita-september2026-row-selector.json";

test("all contributing source intervals remain searchable and keep supply filters in the original row", async ({ page }) => {
  const id = fixture.source_document_id;
  let requestedRow = "";
  await page.route(url => url.pathname === `/api/evidence/${id}`, route => route.fulfill({ json: {
    id, title: fixture.title, publisher: "DANE", kind: "original",
    media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    source_url: fixture.source_url, reference_period: "2026", retrieved_at: "2026-10-04T00:00:00Z",
    bytes: 83247634, page_count: null, metadata: {}, parents: [], records: [fixture.record],
  } }));
  await page.route(url => url.pathname === `/api/evidence/${id}/workbook`, route => {
    const q = new URL(route.request().url()).searchParams;
    const sheet = q.get("sheet") || "Índice";
    requestedRow = q.get("start") || "1";
    const original = fixture.native_cells.find(cell => String(cell.row) === requestedRow);
    const rows = original ? [[
      { value: original.market_literal, type: "text" },
      { value: `${original.date}T00:00:00`, type: "date" },
      ...Array.from({ length: 6 }, () => ({ value: null, type: "blank" })),
      { value: original.food_literal, type: "text" },
      { value: Number(original.cant_kg), type: "number", number_format: "#,##0" },
    ]] : [];
    return route.fulfill({ json: {
      sheets: ["Índice", "2.3"], sheet, start: Number(requestedRow), totalRows: 425246,
      totalColumns: 12, displayedColumns: 12, readOnly: true, rows,
    } });
  });
  const q = new URLSearchParams({ department: "Atlántico", product: "papa-unica",
    productName: "Papa única", market: "sipsa-barranquilla-barranquillita",
    marketName: "Barranquilla, Barranquillita", month: "2026-09-01", units: "kg" });
  await page.goto(`/evidence/${id}?${q}`);
  const supply = page.getByTestId("selected-supply-records");
  await expect(supply).toContainText("3.357.750");
  await expect(supply).toContainText("133");
  await page.getByText("Hoja 2.3 · filas que forman el total", { exact: true }).click();
  await expect(supply).toContainText("Todos los 127 intervalos");
  await expect(supply.getByRole("table")).toHaveCount(0);
  const choice = page.getByRole("group", { name: "Filas originales de la hoja 2.3", exact: true });
  const search = choice.getByRole("combobox");
  let firstChoices: string[] = [];
  for (const query of ["HOJA 2.3", "hója 2.3", "ho\u0301ja 2.3"]) {
    await search.fill(query);
    await expect(choice.getByRole("option")).toHaveCount(8);
    const options = await choice.getByRole("option").allTextContents();
    if (!firstChoices.length) firstChoices = options;
    else expect(options).toEqual(firstChoices);
    await expect(choice).toHaveAttribute("data-selected-value", "232:232");
  }
  // The last interval was inaccessible in the old 100-row table.
  await search.fill("FILA 193051");
  await expect(choice.getByRole("option")).toHaveCount(1);
  await choice.getByRole("option", { name: "Fila 193051 Hoja 2.3", exact: true }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "193051:193051");
  await search.fill("no-existing-row");
  await expect(choice).toHaveAttribute("data-selected-value", "193051:193051");
  await search.press("Escape");
  const rowLink = supply.getByRole("link", { name: "Ver fila 193051 →", exact: true });
  const href = new URL((await rowLink.getAttribute("href"))!, "https://agroamigo.example");
  for (const [key, value] of q) expect(href.searchParams.get(key)).toBe(value);
  expect(href.searchParams.get("sheet")).toBe("2.3");
  expect(href.searchParams.get("row")).toBe("193051");
  await rowLink.click();
  const source = page.getByRole("dialog", { name: "Documento de la fuente", exact: true });
  await expect(source.getByRole("group", { name: "Hoja del archivo Excel", exact: true })).toHaveAttribute("data-selected-value", "2.3");
  await expect(source.locator(".workbook-range")).toContainText("193051");
  await expect(source.locator(".workbook-viewer tbody")).toContainText("Papa única");
  await expect(source.locator(".workbook-viewer tbody")).toContainText("29.000");
  await expect(source.getByLabel("Filtros de los datos consultados", { exact: true })).toContainText("kg");
  expect(requestedRow).toBe("193051");
  await expect(source.locator(".workbook-viewer [contenteditable=true]")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("supply-last-original-row.png"), fullPage: true });
});
