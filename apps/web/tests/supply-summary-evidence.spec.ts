import { test, expect } from "@playwright/test";
import { showsSupplySummaryRecords } from "../src/lib/server/supply-summary-evidence";

const id = "a".repeat(64);
test("daily supply summary is visibly non-additive and opens the original tonnes cells", async ({ page }) => {
  const note = "Abastecimiento diario provisional: 1.268 valores en toneladas, del 2021-11-09 al 2021-12-30. Los blancos indican datos no reportados. Los totales por mercado y el total de los mercados informados se conservan por separado; no se suman a los registros por alimento ni son precios.";
  await page.route("**/api/evidence/**", async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.endsWith("/workbook")) {
      const start = Number(u.searchParams.get("start") || 1);
      const value = (v: unknown, numeric = false) => ({ value: v, type: numeric ? "number" : "text", number_format: numeric ? "#,##0" : "General" });
      await route.fulfill({ json: {
        sheets: ["Índice", "Abastecimiento"], sheet: u.searchParams.get("sheet") || "Índice",
        start, totalRows: 43, totalColumns: 2, displayedColumns: 2, readOnly: true,
        rows: start === 11 ? [[value("Total"), value(21818.382999999998, true)], [value("Armenia, Mercar"), value(422, true)], [value("Dato no reportado"), value(null)]] : [[value("SIPSA")]],
      } });
    } else {
      await route.fulfill({ json: { id, title: "DANE — Anexo diario de abastecimiento", publisher: "DANE", media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", kind: "original", source_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_31_2021.zip", reference_period: "2021-12-31", retrieved_at: "2026-09-28T00:00:00Z", bytes: 1, page_count: null, metadata: { ingestion_kind: "daily-zip-member", supply_summary_note: note, supply_summary_sheet: "Abastecimiento", supply_summary_count: 1560 }, parents: [], records: [{ kind: "supply-daily-summary", quantity_tonnes: 422, unit: "t" }] } });
    }
  });
  await page.goto(`/evidence/${id}`);
  await expect(page.getByTestId("supply-summary-note")).toHaveText(new RegExp("provisional:.*toneladas.*no se suman.*ni son precios"));
  await page.getByRole("link", { name: "Ver celdas originales de abastecimiento" }).click();
  await expect(page).toHaveURL(/sheet=Abastecimiento&row=11/);
  await expect(page.getByRole("group", { name: "Hoja del archivo Excel", exact: true })).toHaveAttribute("data-selected-value", "Abastecimiento");
  await expect(page.locator(".workbook-range")).toContainText("Filas 11–13");
  await expect(page.locator(".workbook-scroll")).toContainText("21.818");
  await expect(page.locator(".workbook-scroll")).toContainText("422");
  await expect(page.getByText("Excel · Solo lectura")).toBeVisible();
  await expect(page.locator(".workbook-scroll input,.workbook-scroll [contenteditable=true]")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("supply-summary.png"), fullPage: true });
});


test("explicit price/crop selection preserves its records instead of supply tonnes", () => {
  for (const key of ["product", "food", "municipality", "input", "department", "market", "month", "future-filter"]) {
    expect(showsSupplySummaryRecords(new URLSearchParams({ [key]: "selected", sheet: "Abastecimiento" }))).toBe(false);
  }
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "Bogotá!row 15,cols D:G,round 1; daily-zip-v1" }))).toBe(false);
  expect(showsSupplySummaryRecords(new URLSearchParams({ sheet: "Abastecimiento", row: "11" }))).toBe(true);
  expect(showsSupplySummaryRecords(new URLSearchParams({ locator: "Abastecimiento!row 12,col 53; supply-daily-summary-v1" }))).toBe(true);
});

test("mixed workbook price cell keeps supply synopsis on its own sheet", async ({ page }) => {
  const note = "Abastecimiento diario provisional: 1.026 valores en toneladas, del 2021-11-09 al 2021-12-20. No son precios.";
  await page.route("**/api/evidence/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/workbook")) {
      const sheet = url.searchParams.get("sheet") || "Cali";
      const value = (text: string | number) => ({ value: text, type: typeof text === "number" ? "number" : "text", number_format: "General" });
      await route.fulfill({ json: {
        sheets: ["Índice", "Abastecimiento", "Cali"], sheet,
        start: Number(url.searchParams.get("start") || 1), totalRows: 120, totalColumns: 7,
        displayedColumns: 7, readOnly: true,
        rows: sheet === "Cali"
          ? [[value("Arroz de primera"), value("Bolsa"), value("25 Unidades 500 GR"), value(28400), value(29000)]]
          : [[value("Abastecimiento"), value(1026)]],
      } });
      return;
    }
    await route.fulfill({ json: {
      id, title: "DANE - Consolidado precios mínimos y máximos diciembre_21_2021.xlsx",
      publisher: "DANE", media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      kind: "original", source_url: "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_diciembre_21_2021.zip",
      reference_period: "2021-12-21", retrieved_at: "2026-09-28T00:00:00Z", bytes: 1, page_count: null,
      metadata: { ingestion_kind: "daily-zip-member", supply_summary_note: note, supply_summary_sheet: "Abastecimiento" },
      parents: [], records: [],
    } });
  });
  await page.goto(`/evidence/${id}?sheet=Cali&row=100&locator=Cali!row%20100,cols%20D:G,round%201;daily-zip-v1`);
  await expect(page.getByText("Arroz de primera")).toBeVisible();
  const otherSheet = page.getByTestId("other-sheet-supply-summary");
  await expect(otherSheet.getByText("Este archivo también contiene abastecimiento (hoja Abastecimiento)")).toBeVisible();
  await expect(otherSheet).not.toHaveAttribute("open", "");
  await expect(page.getByTestId("supply-summary-note")).not.toBeVisible();
  await otherSheet.locator("summary").click();
  await expect(page.getByTestId("supply-summary-note")).toContainText("No son precios");
  await otherSheet.getByRole("link", { name: "Ver celdas originales de abastecimiento" }).click();
  await expect(page).toHaveURL(/sheet=Abastecimiento&row=11/);
  await expect(page.getByTestId("other-sheet-supply-summary")).toHaveCount(0);
  await expect(page.getByTestId("supply-summary-note")).toBeVisible();
});
