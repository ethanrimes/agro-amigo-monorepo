import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

// Oracles read from the original printed Total row on PDF page 5. These dates
// are deliberately pinned so tomorrow's arrivals cannot change the assertion.
const sources = [
  { id: "61b2a8a1d98806033f49bfab42898128e9e590a83e9a8c17edbf287de22afe64", date: "2026-09-24", tonnes: 27004, literal: "27.004", y: "198.99", reported: 220 },
  { id: "1c48c5a321495f34a63b54fda61af13a3f05229051dddac62e66083fb4ee1c78", date: "2026-09-03", tonnes: 26644, literal: "26.644", y: "221.31", reported: 222 },
];

for (const source of sources) test(`daily PDF ${source.date}: original bytes, exact tonnes and provisional page`, async ({ page, request }) => {
  const locator = `PDF page 5, row y${source.y}, column 8; supply-daily-pdf-summary-v1`;
  const query = new URLSearchParams({ locator });
  const response = await request.get(`/api/evidence/${source.id}?${query}`);
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.metadata).toMatchObject({
    supply_summary_count: 264, supply_summary_reported_count: source.reported,
    supply_summary_page: 4,
  });
  expect(data.records).toHaveLength(1);
  expect(data.records[0]).toMatchObject({
    observed_on: source.date, name: "Total", unit: "t", quantity_tonnes: source.tonnes,
    source_locator: locator,
    details: { literal_value: source.literal, provisional_mark: "p", source_page: 5 },
  });
  const original = await request.get(`/api/evidence/${source.id}/content`);
  expect(original.status()).toBe(200);
  expect(createHash("sha256").update(await original.body()).digest("hex")).toBe(source.id);

  await page.goto(`/evidence/${source.id}?${query}`);
  await expect(page.getByTestId("supply-summary-note")).toContainText("las columnas marcadas p son provisionales");
  const table = page.getByTestId("daily-pdf-supply-records");
  await table.locator("summary").click();
  await expect(table).toContainText(source.literal);
  await expect(table).toContainText("Provisional (p)");
  await table.getByRole("link", { name: "Página 5, columna 8" }).click();
  await expect(page.getByRole("group", { name: "Página del documento", exact: true })).toHaveAttribute("data-selected-value", "5");
  await expect(page.locator("canvas[data-rendered=true]")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath(`daily-pdf-supply-${source.date}.png`), fullPage: true });
});
