import { test, expect } from "@playwright/test";
import type { UnifiedCatalog } from "../src/lib/catalog-types";

test("home suggestions open the exact official quote and city selection", async ({ page, request }) => {
  test.setTimeout(90_000);
  const response = await request.get("/api/catalog", { timeout: 90_000 });
  expect(response.ok()).toBe(true);
  const catalog: UnifiedCatalog = await response.json();
  const official = catalog.products.find(p => p.kind === "official-reference" && p.currency === "USD" && p.name.includes("Café"))!;
  const city = catalog.products.find(p => p.series === "city")!;
  expect(official).toBeTruthy();
  expect(city).toBeTruthy();
  for (const product of [official, city]) {
    await page.route("**/api/catalog*", route => route.fulfill({ json: { ...catalog, products: [product] } }));
    await page.goto("/");
    await page.getByRole("combobox", { name: "Buscar un producto" }).fill(product.name);
    await page.getByRole("option").click();
    const expected = new URL(product.href!, "http://localhost");
    await expect(page).toHaveURL(url => url.pathname === expected.pathname);
    const actual = new URL(page.url());
    for (const [key, value] of expected.searchParams) expect(actual.searchParams.get(key)).toBe(value);
    expect(actual.searchParams.get("returnTo")).toBe("/products?q=" + encodeURIComponent(product.name));
    await expect(page.locator("h1")).toContainText(product.name);
    if (product.kind === "official-reference") {
      await expect(page.locator(".current-product-price")).toHaveAttribute("data-currency", "USD");
      await expect(page.locator(".current-product-price")).toHaveAttribute("data-price", String(product.price));
    }
    await page.unroute("**/api/catalog*");
  }
});

test("home keeps navigation usable when section photographs fail", async ({ page }) => {
  await page.route("**/images/library/*.jpg", route => route.abort());
  await page.goto("/");
  for (const path of ["/markets", "/insumos"]) {
    const section = page.locator(`.home-section[href="${path}"]`);
    await expect(section.locator(".home-section-placeholder svg")).toBeVisible();
    await expect(section.locator("img")).toHaveCount(0);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.home-section[href="/markets"]').click();
  await expect(page).toHaveURL(/\/markets$/);
});
