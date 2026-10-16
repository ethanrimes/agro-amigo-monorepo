import { test, expect } from "@playwright/test";
import path from "node:path";
import { showsSupplySummaryRecords } from "../src/lib/server/supply-summary-evidence";

const id = "b".repeat(64);
const locator = "PDF page 5, row y198.99, column 8; supply-daily-pdf-summary-v1";

test("daily PDF supply locator is visible without admitting a price filter", () => {
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator }))).toBe(true);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator, product: "selected" }))).toBe(false);
});

test("daily PDF table shows exact provisional tonne evidence and opens the printed page", async ({ page }) => {
  await page.route(`**/api/evidence/${id}**`, async route => {
    if (new URL(route.request().url()).pathname.endsWith("/content")) {
      return route.fulfill({
        path: path.resolve(__dirname, "../../../pipelines/ingestion/testdata/bol-SIPSADiario-25sep2026.pdf"),
        contentType: "application/pdf",
      });
    }
    return route.fulfill({ json: {
      id, title: "DANE — Boletín diario 25 de septiembre de 2026", publisher: "DANE",
      media_type: "application/pdf", kind: "original", source_url: "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-25sep2026.pdf",
      reference_period: "2026-09-25", retrieved_at: "2026-09-29T00:00:00Z", bytes: 348822,
      page_count: 6, parents: [], metadata: {
        ingestion_kind: "daily-pdf", supply_summary_count: 264,
        supply_summary_page: 4,
        supply_summary_note: "Abastecimiento diario (las columnas marcadas p son provisionales): 220 valores en toneladas, del 2026-09-17 al 2026-09-24.",
      },
      records: [{ kind: "supply-daily-summary", observed_on: "2026-09-24", name: "Total",
        source_locator: locator, details: { quantity_tonnes: 27004, source_page: 5, column: 8, provisional_mark: "p" } }],
    } });
  });
  await page.goto(`/evidence/${id}`);
  await expect(page.getByTestId("supply-summary-note")).toContainText("las columnas marcadas p son provisionales");
  await page.getByText("Abastecimiento diario: 1 celdas del Cuadro 1").click();
  await expect(page.getByTestId("daily-pdf-supply-records")).toContainText("27.004");
  await expect(page.getByTestId("daily-pdf-supply-records")).toContainText("Provisional (p)");
  await page.getByRole("link", { name: "Página 5, columna 8" }).click();
  await expect(page.getByRole("group", { name: "Página del documento", exact: true })).toHaveAttribute("data-selected-value", "5");
});
