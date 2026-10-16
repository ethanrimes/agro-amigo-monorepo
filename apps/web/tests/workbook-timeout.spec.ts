import { expect, test } from "@playwright/test";

test("a source workbook stays open beyond the ordinary JSON deadline and renders its unchanged cells", async ({ page }) => {
  test.setTimeout(60_000);
  const id = "f193e21732852ab19f63e788e8cb9e1735e57b5e6c9e277fbda0f3ee8e007c32";
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let requested!: () => void;
  const started = new Promise<void>(resolve => { requested = resolve; });
  await page.route(url => url.pathname === `/api/evidence/${id}`, route => route.fulfill({ json: {
    id, title: "DANE - anex-Microdato-abastecimiento-2026.xlsx", publisher: "DANE",
    media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    source_url: "https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2026.xlsx",
    reference_period: "2026", kind: "original", retrieved_at: "2026-10-12", bytes: 85506385,
    metadata: {}, records: [], parents: [],
  } }));
  await page.route(url => url.pathname === `/api/evidence/${id}/workbook`, async route => {
    requested();
    await pending;
    await route.fulfill({ json: {
      sheets: ["Índice", "2.2"], sheet: "2.2", start: 602025,
      totalRows: 787345, totalColumns: 2, displayedColumns: 2, readOnly: true,
      rows: [[{ value: "Papa capira", type: "text" }, { value: 5000, type: "number", number_format: "#,##0" }]],
    } });
  });
  try {
    await page.goto(`/evidence/${id}?sheet=2.2&row=602025&marketName=Armenia%2C+Mercar&productName=Papa+capira`);
    await started;
    await page.waitForTimeout(31_000);
    await expect(page.getByText("Abriendo hoja…", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No pudimos cargar los datos" })).toHaveCount(0);
    release();
    await expect(page.locator(".workbook-scroll")).toContainText("Papa capira");
    await expect(page.locator(".workbook-scroll")).toContainText("5.000");
    await expect(page.locator(".workbook-range")).toContainText("602025");
    await expect(page.locator(".workbook-viewer [contenteditable=true]")).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath("workbook-after-ordinary-deadline.png"), fullPage: true });
  } finally {
    release();
  }
});
