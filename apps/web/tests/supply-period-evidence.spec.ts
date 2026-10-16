import { test, expect } from "@playwright/test";
import path from "node:path";
import { showsSupplySummaryRecords } from "../src/lib/server/supply-summary-evidence";
import { workbookLocation } from "../src/lib/workbook-locator";
const id = "a".repeat(64);
const note = "Abastecimiento por período (mes completo): 28 celdas de toneladas y 14 de porcentajes, del 2012-12-01 al 2013-01-31. Se conserva la precisión de cada original; los PDF pueden estar redondeados. Son resúmenes no aditivos: no se incorporan a los registros por alimento o a los precios.";

test("monthly PDF note separates earlier comparison month, units, and native table", async ({ page }) => {
  await page.route("**/api/evidence/**", async route => {
    if (new URL(route.request().url()).pathname.endsWith("/content")) {
      await route.fulfill({ path: path.resolve(__dirname, "../../../artifacts/source-verification-2026-09-28/supply-reference-audit/originals/bol_abas_ene13.pdf"), contentType: "application/pdf" });
    } else await route.fulfill({ json: { id, title: "DANE — Abastecimiento enero de 2013", publisher: "DANE", media_type: "application/pdf", kind: "original", source_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_abas_ene13.pdf", reference_period: "2013-01-31", retrieved_at: "2026-09-28T00:00:00Z", bytes: 1, page_count: 8, metadata: { ingestion_kind: "supply-reference-pdf", supply_summary_note: note, supply_summary_page: 4, supply_summary_count: 42 }, parents: [], records: [] } });
  });
  await page.goto(`/evidence/${id}`);
  await expect(page.getByTestId("supply-summary-note")).toContainText("2012-12-01 al 2013-01-31");
  await expect(page.getByTestId("supply-summary-note")).toContainText("toneladas y 14 de porcentajes");
  await page.getByRole("link", { name: "Ver tabla original de abastecimiento" }).click();
  await expect(page.getByRole("group", { name: "Página del documento", exact: true })).toHaveAttribute("data-selected-value", "4");
  await expect(page.locator(".pdf-paper canvas[data-rendered=true]")).toBeVisible();
  await expect(page.getByTestId("supply-summary-note")).toContainText("no aditivos");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("period-pdf.png"), fullPage: true });
});

test("period cell locators preserve explicit price filters", () => {
  for (const locator of ["1!row 11,col 4; supply-period-summary-v1", "1!row 40,col 4; supply-period-summary-workbook-v2", "PDF page 4, row y218.33, column 2; supply-period-summary-v1", "PDF page 2, row y176.26, column 2; supply-period-summary-v2", "PDF page 4, row y182.93, column 2; supply-period-summary-v3", "PDF page 4, OCR table 1, row 2, column 2; supply-period-summary-v4", "PDF page 4, OCR table 1, row 2, column 3; supply-period-summary-v5", "PDF page 4, OCR table 1, row 2, column 4; supply-period-summary-v6", "PDF page 4, OCR table 1, row 2, column 2; printed-row-v2; supply-period-summary-v8", "PDF page 4, OCR table 1, row 31, column 3; printed-row-v2; supply-period-summary-v8", "PDF page 3, OCR table 1, row 31, column 4; printed-row-v2; supply-period-summary-v8"]) {
    expect(showsSupplySummaryRecords(new URLSearchParams({ locator }))).toBe(true);
    for (const key of ["product", "food", "market", "month", "municipality", "department", "input", "unknown-filter"]) {
      expect(showsSupplySummaryRecords(new URLSearchParams({ locator, [key]: "selected" }))).toBe(false);
    }
  }
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "1!row 11,col 4; other-parser" }))).toBe(false);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "PDF page 4, OCR table 1, row 2, column 9; supply-period-summary-v6" }))).toBe(false);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "PDF page 4, OCR table 1, row 2, column 1; supply-period-summary-v6" }))).toBe(false);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "PDF page 4, OCR table 1, row 2, column 1; printed-row-v2; supply-period-summary-v8" }))).toBe(false);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "1!row 11,col 4; printed-row-v2; supply-period-summary-v8" }))).toBe(false);
});

test("a workbook locator opens its exact sheet and row", async ({ page }) => {
  const locator = "1!row 40,col 4; supply-period-summary-workbook-v2";
  let workbookQuery = new URLSearchParams();
  expect(workbookLocation(locator)).toEqual({ sheet: "1", row: 40, column: 4 });
  expect(workbookLocation("Boletín diario!V18")).toEqual({ sheet: "Boletín diario", row: 18, column: 22 });
  expect(workbookLocation("Boletín diario!v18")).toEqual({ sheet: "Boletín diario", row: 18, column: 22 });
  expect(workbookLocation("PDF page 4, row y218.33, column 2")).toBeNull();
  await page.route(url => url.pathname === `/api/evidence/${id}`, route => route.fulfill({ json: {
    id, title: "DANE — Abastecimiento abril de 2024", publisher: "DANE",
    media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    kind: "original", source_url: "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAabastecimiento-1raquinabril2024.xlsx",
    reference_period: "2024-04-15", retrieved_at: "2026-09-29T00:00:00Z",
    bytes: 239667, page_count: null, metadata: { ingestion_kind: "supply-reference", supply_summary_count: 983 },
    parents: [], records: [],
  } }));
  await page.route(url => url.pathname === `/api/evidence/${id}/workbook`, route => {
    workbookQuery = new URL(route.request().url()).searchParams;
    const selectedSheet = workbookQuery.get("sheet") || "1";
    return route.fulfill({ json: {
    sheets: ["Índice", "1"], sheet: selectedSheet, start: selectedSheet === "1" ? 40 : 1, totalRows: 40,
    totalColumns: 4, displayedColumns: 4, readOnly: true,
    rows: [[{ value: "TOTAL", type: "text" }, { value: null, type: "blank" }, { value: null, type: "blank" }, { value: 307711.52209999994, type: "number" }]],
    } });
  });
  await page.goto(`/evidence/${id}?locator=${encodeURIComponent(locator)}`);
  await expect(page.getByRole("group", { name: "Hoja del archivo Excel", exact: true })).toHaveAttribute("data-selected-value", "1");
  await expect(page.locator(".workbook-range")).toContainText("Filas 40");
  await expect(page.locator(".workbook-source-cell")).toContainText("307.711,5221");
  await expect(page.locator(".workbook-source-cell")).toHaveAttribute("aria-label", "Celda D40 de la fuente");
  await expect.poll(() => page.evaluate(() => {
    const viewport = document.querySelector(".workbook-scroll")!.getBoundingClientRect();
    const cell = document.querySelector(".workbook-source-cell")!.getBoundingClientRect();
    return cell.left >= viewport.left && cell.right <= viewport.right;
  })).toBe(true);
  expect(workbookQuery.get("sheet")).toBe("1");
  expect(workbookQuery.get("start")).toBe("40");
  await page.getByRole("combobox", { name: "Hoja del archivo Excel" }).fill("Índice");
  await page.getByRole("option", { name: "Índice", exact: true }).click();
  await expect(page.getByRole("group", { name: "Hoja del archivo Excel", exact: true })).toHaveAttribute("data-selected-value", "Índice");
  await expect(page.locator(".workbook-source-cell")).toHaveCount(0);
});
