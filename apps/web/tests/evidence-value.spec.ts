import { test, expect } from "@playwright/test";
import { evidenceValue } from "../src/lib/evidence-value";

test("original EVA and calendar years and physical row identifiers stay ungrouped", () => {
  expect(evidenceValue("reference_year", 2025)).toBe("2025");
  expect(evidenceValue("reference_year", 2024)).toBe("2024");
  expect(evidenceValue("source_row", 15935)).toBe("15935");
  expect(evidenceValue("source_rows", [15935, 15936])).toBe("15935 · 15936");
  expect(evidenceValue("source_locator", "Hoja 1!E15935")).toBe("Hoja 1!E15935");
});

test("measured quantities and prices retain existing Spanish formatting", () => {
  expect(evidenceValue("price", 2025)).toBe("2.025");
  expect(evidenceValue("production_t", 9900)).toBe("9.900");
  expect(evidenceValue("yield_kg_ha", 1868.88888888889)).toBe("1.868,9");
  expect(evidenceValue("price", 11262.5)).toBe("11.262,5");
});

test("original arrays and missing or structured values retain their content", () => {
  expect(evidenceValue("percentages", [11.67, 20, 28.759999999999994])).toBe(
    "11.67 · 20 · 28.759999999999994",
  );
  expect(evidenceValue("yield_kg_ha", null)).toBe("Sin dato");
  expect(evidenceValue("details", { period: "2025A" })).toBe('{"period":"2025A"}');
  // Invalid fractional identifiers must not be rounded into an invented row/year.
  expect(evidenceValue("source_row", 12.5)).toBe("12,5");
});
