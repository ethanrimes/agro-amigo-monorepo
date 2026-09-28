import { test, expect } from "@playwright/test";

test("worksheet option values preserve exact source names when selecting a trailing-space sheet", async ({ page }) => {
  const requestedSheets: string[] = [];
  await page.route("**/api/evidence/worksheet-identity?*", route => route.fulfill({ json: {
    id: "worksheet-identity", title: "Original con nombres de hoja literales", publisher: "DANE",
    source_url: "https://www.dane.gov.co/original.xlsx", media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    kind: "original", reference_period: "2014-02-05", retrieved_at: "2026-09-28T00:00:00Z",
    bytes: 1024, page_count: null, metadata: {}, parents: [], records: [],
  } }));
  await page.route("**/api/evidence/worksheet-identity/workbook?*", route => {
    const sheet = new URL(route.request().url()).searchParams.get("sheet") || "Overview";
    requestedSheets.push(sheet);
    // The source parser selects exact worksheet identities. A trimmed name is invalid.
    if (!["Overview", "Prices "].includes(sheet)) return route.fulfill({ status: 400, json: { error: "Unknown source worksheet" } });
    return route.fulfill({ json: {
      sheets: ["Overview", "Prices "], sheet, start: 1, totalRows: 1, totalColumns: 1, displayedColumns: 1,
      rows: [[{ type: "string", value: sheet === "Overview" ? "Source overview" : "Exact price worksheet" }]], readOnly: true,
    } });
  });
  await page.goto("/evidence/worksheet-identity?sheet=Overview");
  const picker = page.getByRole("combobox", { name: "Hoja del archivo Excel" });
  await expect(page.locator(".workbook-scroll")).toContainText("Source overview");
  await picker.selectOption({ index: 1 });
  await expect.poll(() => requestedSheets.at(-1)).toBe("Prices ");
  await expect(picker).toHaveValue("Prices ");
  await expect(picker.locator("option").nth(1)).toHaveAttribute("value", "Prices ");
  await expect(page.locator(".workbook-scroll")).toContainText("Exact price worksheet");
  await expect(page.locator(".workbook-scroll [contenteditable=true]")).toHaveCount(0);
  await picker.selectOption({ index: 0 });
  await expect.poll(() => requestedSheets.at(-1)).toBe("Overview");
  await expect(page.locator(".workbook-scroll")).toContainText("Source overview");
});
