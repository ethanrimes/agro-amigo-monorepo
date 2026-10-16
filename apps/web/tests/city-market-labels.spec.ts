import { expect, test } from "@playwright/test";

test("one verified city market choice keeps all its original reports and source context", async ({ page }) => {
  const names = ["Bogotá, Corabastos", "Bogotá D.C., Corabastos", "Bogotá, D.C., Corabastos", "Bogotà, Corabastos"];
  const canonical = "Bogotá, D.C., Corabastos";
  const rows = names.map((market_name, index) => ({
    product_id: "limon-tahiti", product_name: "Limón Tahití", market_name,
    display_market_name: canonical, market_id: "sipsa-bogota-d-c-corabastos",
    market_region: "Bogotá, D.C.", category_path: ["Frutas", "Cítricos"],
    document_id: String(index + 1).repeat(64), source_page: 1,
    source_locator: `PDF page 1,table 1,row ${index + 1},round 2`,
    observed_on: "2026-10-07", presentation: "Bulto", quantity: 20 + index,
    source_unit: "Kilogramo", round: 2, round_label: "Ronda 2",
    min_price: 100 + index, max_price: 110 + index, unit: "kg",
    min_unit_price: null, max_unit_price: null,
  }));
  // Unverified locations must remain separate; this is not a fuzzy name merge.
  const unknown = { ...rows[0], document_id: "a".repeat(64),
    market_id: null, market_region: null, market_name: "Corabastos sin ubicación verificada",
    display_market_name: "Corabastos sin ubicación verificada" };
  await page.route("**/api/**", route => route.fulfill({
    json: new URL(route.request().url()).pathname === "/api/planning/regional"
      ? [...rows, unknown] : [],
  }));
  await page.goto("/regional");
  await expect(page.locator(".input-card")).toHaveCount(5);
  const market = page.getByRole("group", { name: "Mercado del informe", exact: true });
  for (const query of ["BOGOTA", "bogotá", "Bogota\u0301"]) {
    await market.getByRole("combobox").fill(query);
    await expect(market.getByRole("option")).toHaveCount(1);
    await expect(market.getByRole("option")).toHaveText(canonical);
  }
  await market.getByRole("option").click();
  await expect(page.locator(".input-card")).toHaveCount(4);
  await expect(page.getByText(`Mercado: ${canonical}`, { exact: true })).toBeVisible();
  for (const [index, row] of rows.entries()) {
    const card = page.locator(".input-card").nth(index);
    await expect(card.locator(".eyebrow")).toHaveText(canonical);
    const source = new URL((await card.getByRole("link", { name: /Consultar fuente/ }).getAttribute("href"))!, "https://example.invalid");
    expect(source.pathname).toBe(`/evidence/${row.document_id}`);
    expect(source.searchParams.get("marketName")).toBe(row.market_name);
    expect(source.searchParams.get("locator")).toBe(row.source_locator);
    expect(source.searchParams.get("units")).toBe(`${row.quantity} Kilogramo`);
    expect(source.searchParams.get("month")).toBe("2026-10-07");
    const product = new URL((await card.getByRole("link", { name: "Limón Tahití", exact: true }).getAttribute("href"))!, "https://example.invalid");
    expect(product.searchParams.get("market")).toBe(row.market_id);
    expect(product.searchParams.get("region")).toBe(row.market_region);
    expect(product.searchParams.get("units")).toBe(`${row.quantity} Kilogramo`);
  }
  await market.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(page.locator(".input-card")).toHaveCount(5);
  await market.getByRole("combobox").fill("sin ubicacion");
  await market.getByRole("option").click();
  await expect(page.locator(".input-card")).toHaveCount(1);
  await expect(page.locator(".input-card .eyebrow")).toHaveText(unknown.market_name);
});
