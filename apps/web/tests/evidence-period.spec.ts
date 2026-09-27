import { test, expect } from "@playwright/test";
import { evidencePeriod } from "../src/lib/evidence-period";
import type { Evidence } from "../src/lib/planning-types";

// Original Barranquillita25-09-2026.pdf; rows are validated from the printed PDF,
// not inferred from its filename or the enclosing ZIP URL.
const city = {
  id: "6f6427903f2879d35e6032601f4cdc1e4ef7b66cb8648155b2353a0a6c55ac30",
  title: "Barranquillita25-09-2026.pdf", publisher: "DANE",
  reference_period: "Serie histórica completa", media_type: "application/pdf",
  kind: "original", retrieved_at: "2026-09-27T00:00:00Z", bytes: 100,
  page_count: 1, source_url: "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-25sep2026.zip",
  metadata: { ingestion_kind: "city-pdf" }, parents: [],
  records: [{ observed_on: "2026-09-25", product_name: "Mora de castilla", min_price: 78000, max_price: 80000 }],
} as Evidence;
test("city PDF period uses its verified observation date rather than generic archive metadata", () => {
  expect(evidencePeriod(city)).toBe("25 de septiembre de 2026");
  expect(city.reference_period).toBe("Serie histórica completa");
});
test("city PDF spanning multiple verified days preserves its range", () => {
  expect(evidencePeriod({ ...city, records: [{ observed_on: "2026-09-25" }, { observed_on: "2026-09-24" }] })).toBe("24 de septiembre de 2026 al 25 de septiembre de 2026");
});
test("missing or invalid city dates never infer a date from filename or neighboring row", () => {
  for (const records of [[], [{}], [{ observed_on: "2026-02-30" }], [{ observed_on: "2026-09-25" }, {}]])
    expect(evidencePeriod({ ...city, records })).toBe("Serie histórica completa");
});
test("a filtered historical workbook preview cannot narrow the whole source period", () => {
  expect(evidencePeriod({ ...city, metadata: { ingestion_kind: "international-worldbank" }, media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })).toBe("Serie histórica completa");
});
test("source heading presents the verified city day", async ({ page }) => {
  await page.route("**/api/evidence/**", (route) => route.fulfill({ json: { ...city, media_type: "application/json" } }));
  await page.goto("/evidence/" + city.id);
  await expect(page.locator(".evidence-heading")).toContainText("DANE · Referencia: 25 de septiembre de 2026");
  await expect(page.locator(".evidence-heading")).not.toContainText("Serie histórica completa");
});
