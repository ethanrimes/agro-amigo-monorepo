import { test, expect } from "@playwright/test";

// Literal EVA 2025 / SIPSA names from the live September 27 audit.
// The kg unit alone cannot make canned peas or pods equivalent to harvested grain.
test("grain budget excludes canned and pod peas while preserving explicit manual pricing", async ({ page }) => {
  const municipality = { id: "41551", name: "PITALITO", department: "HUILA", department_id: "41", latitude: 1.852631, longitude: -76.049441 };
  const crop = { crop_code: "1060100", crop: "Arveja", variety: "Arveja", reference_year: 2025, cycle: "Transitorio", physical_state: "Grano", planted_ha: 1, harvested_ha: 1, production_t: 1, yield_kg_ha: 1000, document_id: "audit-eva", source_rows: [1] };
  const names = ["Arveja enlatada", "Arveja verde en vaina", "Arveja verde en vaina pastusa", "Arveja amarilla seca importada", "Arveja verde seca importada"];
  const requests: string[] = [];
  await page.addInitScript(() => localStorage.setItem("agroamigo-farm-v1", JSON.stringify({ municipalityId: "41551", name: "QA Arveja", cropCode: "1060100", variety: "Arveja", area: "1", stage: "harvest", plantingDate: "", floweringDate: "", irrigation: false, latitude: "", longitude: "", elevation: "" })));
  await page.route("**/api/**", route => {
    const u = new URL(route.request().url());
    if (u.pathname === "/api/planning/farm") return route.fulfill({ json: { municipality, crops: [crop], calendars: [], suitability: [], soil: null, templates: [], advisories: [] } });
    if (u.pathname === "/api/catalog") {
      requests.push(u.search);
      return route.fulfill({ json: { products: names.map((name, i) => ({ id: "pea-" + i, name, kind: "product", currency: "COP", unit: "kg", series: "monthly" })), regions: [], latestDate: "2026-08-31" } });
    }
    if (u.pathname.startsWith("/api/products/")) return route.fulfill({ json: { markets: [] } });
    return route.fulfill({ status: 503, json: { error: "Unrelated fixture" } });
  });
  await page.goto("/plan?tab=budget");
  const picker = page.getByLabel("Producto y presentación que venderías");
  await expect(picker.locator("option")).toHaveText(["Selecciona una presentación", "Arveja amarilla seca importada", "Arveja verde seca importada"]);
  expect(requests).toContain("?view=canonical");
  await page.getByRole("button", { name: "Ingresar mi precio", exact: true }).click();
  await page.getByLabel("Precio que recibirías por kg (COP)").fill("2500");
  await expect(page.getByLabel("Precio que recibirías por kg (COP)")).toHaveValue("2500");
  await page.getByLabel("Área (hectáreas)", { exact: true }).fill("2");
  await page.getByLabel("Cosecha de referencia (kg por hectárea)").fill("1000");
  await page.getByLabel("Pérdida o producto no vendible (%)").fill("10");
  for (const [label, value] of [
    ["Preparación, siembra y labores por hectárea", "200000"],
    ["Semilla e insumos por hectárea", "300000"],
    ["Cosecha y poscosecha por hectárea", "100000"],
    ["Otros costos de producción por hectárea", "0"],
  ]) await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByLabel("Precio que recibirías por kg (COP)").fill("2000");
  await page.getByLabel("Gastos adicionales de venta, total (COP)").fill("100000");
  await page.getByLabel("Comisión sobre la venta (%)").fill("10");
  await expect(page.locator(".earnings-scenarios .typical strong")).toContainText("1.940.000");
  await expect(page.locator(".break-even strong")).toContainText("802");

});
