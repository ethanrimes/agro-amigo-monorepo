import { test, expect } from "@playwright/test";
import path from "node:path";
import { showsSupplySummaryRecords } from "../src/lib/server/supply-summary-evidence";
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
  await expect(page.getByLabel("Página del documento")).toHaveValue("4");
  await expect(page.locator(".pdf-paper canvas[data-rendered=true]")).toBeVisible();
  await expect(page.getByTestId("supply-summary-note")).toContainText("no aditivos");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("period-pdf.png"), fullPage: true });
});

test("period cell locators preserve explicit price filters", () => {
  for (const locator of ["1!row 11,col 4; supply-period-summary-v1", "PDF page 4, row y218.33, column 2; supply-period-summary-v1"]) {
    expect(showsSupplySummaryRecords(new URLSearchParams({ locator }))).toBe(true);
    for (const key of ["product", "food", "market", "month", "municipality", "department", "input", "unknown-filter"]) {
      expect(showsSupplySummaryRecords(new URLSearchParams({ locator, [key]: "selected" }))).toBe(false);
    }
  }
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "1!row 11,col 4; other-parser" }))).toBe(false);
});
