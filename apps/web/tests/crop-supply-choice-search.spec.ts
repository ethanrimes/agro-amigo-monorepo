import { expect, test } from "@playwright/test";
import { EMPTY_PROFILE } from "../src/lib/farm-types";

for (const count of [4, 12]) {
  test(`municipal crop references preserve all ${count} identities with a bounded exact selector`, async ({ page }) => {
    await page.addInitScript((profile) => localStorage.setItem("agroamigo-farms-v2", JSON.stringify({ version: 2, activeId: "fixture-farm", farms: [{ id: "fixture-farm", profile: { ...profile, name: "Finca de prueba", municipalityId: "41551" }, crops: [], selectedCropId: "" }] })), EMPTY_PROFILE);
    const municipality = { id: "41551", name: "Pitalito", department: "Huila", latitude: 1.85, longitude: -76.05 };
    const crops = Array.from({ length: count }, (_, index) => ({ crop_code: `crop-${index}`, crop: "Frutales", variety: index === count - 1 ? "Último cultivo" : `Variedad ${index + 1}`, cycle: "Permanente", physical_state: "Fresco", harvested_ha: 10, yield_kg_ha: 1000, reference_year: 2024, document_id: String(index + 1).padStart(64, "0") }));
    await page.route("**/api/planning/municipalities", (route) => route.fulfill({ json: [municipality] }));
    await page.route("**/api/location/layers", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/planning/farm?**", (route) => route.fulfill({ json: { municipality, crops, suitability: [], calendars: [], advisories: [], templates: [], soil: null } }));
    await page.goto("/farm");
    await page.getByRole("button", { name: "¿Qué se cultiva en este municipio?", exact: true }).click();
    const cards = page.locator(".crop-option");
    await expect(cards).toHaveCount(count > 9 ? 0 : count);
    const choice = page.getByRole("group", { name: "Consultar cultivo reportado", exact: true });
    const search = choice.getByRole("combobox");
    await search.click();
    await expect(choice.getByRole("option")).toHaveCount(Math.min(count, 8));
    await search.fill("ultimo cultivo");
    await expect(cards).toHaveCount(count > 9 ? 0 : count);
    await choice.getByRole("option", { name: /Último cultivo/ }).click();
    await expect(cards).toHaveCount(1);
    await expect(cards.getByRole("heading", { name: "Último cultivo", exact: true })).toBeVisible();
    await expect(cards.getByRole("link", { name: /Ver calendario y fuentes/ })).toHaveAttribute("href", new RegExp(`crop=crop-${count - 1}`));
    await search.fill("no-matching-crop-zzzz");
    await expect(cards).toHaveCount(1);
    await search.press("Escape");
    await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
    await expect(cards).toHaveCount(count > 9 ? 0 : count);
  });
}

test("supply search reaches an old month and a distant report without rendering the full history or report list", async ({ page }) => {
  const history = Array.from({ length: 36 }, (_, index) => ({ date: `${2020 + Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}-01`, quantity_kg: 105_000 }));
  await page.route("**/api/products/fixture-product?**", (route) => route.fulfill({ json: { product: { id: "fixture-product", name: "Ahuyama", category: "Hortalizas", image_key: "produce" }, markets: [], classification: [["Hortalizas"]], additional_references: [], history: [], filters: {}, options: { series: [], presentations: [], units: [], markets: [] } } }));
  await page.route("**/api/explore/supply?**", (route) => {
    const selected = new URL(route.request().url()).searchParams.get("month") || history[35].date;
    const rows = Array.from({ length: 14 }, (_, index) => ({ market_id: `market-${index}`, market_name: index === 13 ? "Último mercado" : `Plaza ${index + 1}`, food_id: "ahuyama", food_name: "Ahuyama", product_id: "fixture-product", quantity_kg: 14_000 - index * 1_000, period_start: selected, first_reported_on: selected, observed_on: selected, reporting_days: 1, document_id: String(index + 1).padStart(64, "0"), region: "Huila" }));
    return route.fulfill({ json: { rows, history, latest_period: history[35].date, selected_period: selected } });
  });
  await page.goto("/product/fixture-product");
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await expect(page.locator(".supply-bars button")).toHaveCount(12);
  await expect(page.locator(".supply-list article")).toHaveCount(6);
  const month = page.getByRole("group", { name: "Mes de consulta", exact: true });
  await month.getByRole("combobox").fill("2020-01-01");
  await expect(month).toHaveAttribute("data-selected-value", "2022-12-01");
  await month.getByRole("option", { name: /2020-01-01/ }).click();
  await expect(month).toHaveAttribute("data-selected-value", "2020-01-01");
  await expect(page.locator(".supply-bars button")).toHaveCount(13);
  await expect(page.locator('.supply-bars button[aria-pressed="true"]')).toHaveAccessibleName(/enero de 2020/);
  const report = page.getByRole("group", { name: "Consultar llegada reportada", exact: true });
  const search = report.getByRole("combobox");
  await search.click();
  await expect(report.getByRole("option")).toHaveCount(8);
  await search.fill("ultimo mercado");
  await report.getByRole("option", { name: /Último mercado/ }).click();
  await expect(page.locator(".supply-list article")).toHaveCount(7);
  const chosen = page.locator(".supply-list article").filter({ hasText: "Último mercado" });
  await expect(chosen).toContainText("1 t");
  await expect(chosen.getByRole("link", { name: "Comprobar cantidad", exact: true })).toHaveAttribute("href", /market=market-13.*month=2020-01-01/);
  await search.fill("no-matching-report-zzzz");
  await expect(chosen).toBeVisible();
  await search.press("Escape");
  await report.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(page.locator(".supply-list article")).toHaveCount(6);
});
