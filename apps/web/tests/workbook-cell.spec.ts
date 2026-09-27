import { test, expect } from "@playwright/test";
import { workbookCellText } from "../src/lib/workbook-cell";

test("native DANE percentages retain source scaling and precision", () => {
  // anex-SIPSADiario-25sep2026.xlsx E6, G6 and K6, original 0% formats.
  for (const [value, expected] of [[-0.02, "-2%"], [0, "0%"], [0.02, "2%"]] as const)
    expect(workbookCellText({ value, type: "number", number_format: "0%" })).toBe(expected);
  expect(workbookCellText({ value: 0.01234, type: "number", number_format: "0.00%" })).toBe("1,23%");
  expect(workbookCellText({ value: -0.01234, type: "number", number_format: "0%;[Red](0.00%);0.0%" })).toBe("(1,23%)");
  expect(workbookCellText({ value: 0, type: "number", number_format: "0%;[Red](0.00%);0.0%" })).toBe("0,0%");
});

test("literal percent signs and text never rescale source data", () => {
  for (const number_format of ['0.00"%"', "0.00\\%"])
    expect(workbookCellText({ value: 0.02, type: "number", number_format })).toBe("0,02%");
  expect(workbookCellText({ value: "n.d.", type: "text", number_format: "0%" })).toBe("n.d.");
  expect(workbookCellText({ value: "0.02", type: "text", number_format: "0%" })).toBe("0.02");
  expect(workbookCellText({ value: null, type: "text", number_format: "0%" })).toBe("");
});

test("normal quotes, dates and unformatted historical files retain raw values", () => {
  expect(workbookCellText({ value: 2338, type: "number", number_format: "#,##0" })).toBe("2.338");
  expect(workbookCellText({ value: 2120.976861274773, type: "number" })).toBe("2.120,976861274773");
  expect(workbookCellText({ value: "2012-07-31T00:00:00", type: "date" })).toBe("2012-07-31T00:00:00");
});

test("source viewer renders percentages while retaining read-only sheet navigation", async ({ page }) => {
  const id = "5fc9d3a1d781".padEnd(64, "0");
  await page.route(new RegExp(`/api/evidence/${id}(?:\\?.*)?$`), route => route.fulfill({ json: {
    id, title: "DANE daily workbook", publisher: "DANE", media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    reference_period: "2026-09-25", kind: "original", retrieved_at: "2026-09-27", bytes: 100,
    metadata: {}, records: [], parents: [], source_url: "https://www.dane.gov.co/",
  } }));
  await page.route(`**/api/evidence/${id}/workbook?**`, route => {
    expect(new URL(route.request().url()).searchParams.get("format")).toBe("native-formats-v2");
    return route.fulfill({ json: {
      sheets: ["Precios"], sheet: "Precios", start: 6, totalRows: 6, totalColumns: 4, displayedColumns: 4, readOnly: true,
      rows: [[{ value: "n.d.", type: "text" }, ...[-0.02, 0, 0.02].map(value => ({ value, type: "number", number_format: "0%" }))]],
    } });
  });
  await page.goto(`/evidence/${id}`);
  await expect(page.locator(".workbook-viewer tbody td")).toHaveText(["n.d.", "-2%", "0%", "2%"]);
  await expect(page.getByText("Excel · Solo lectura", { exact: true })).toBeVisible();
  await expect(page.locator(".workbook-viewer [contenteditable=true]")).toHaveCount(0);
});
