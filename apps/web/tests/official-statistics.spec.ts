import { test, expect } from "@playwright/test";
import type { OfficialPrice } from "../src/lib/official-types";

for (const statistic of ["published_mean", "range_midpoint", undefined]) {
  test(`reference distinguishes the published mean from a midpoint: ${statistic || "unspecified"}`, async ({ page }) => {
    const quote: OfficialPrice = {
      quote_key: "a".repeat(64), product_id: "tomate-chonto", product_name: "Tomate chonto",
      category: "Verduras y hortalizas", publisher: "DANE · SIPSA", series: "dane-weekly",
      basis: "Precio mayorista semanal", currency: "COP", unit: "kg", market: "Bogotá, Corabastos",
      observed_on: "2026-09-25", period_start: "2026-09-19",
      price: statistic === "range_midpoint" ? 110 : 100, min_price: 90, max_price: 130,
      document_id: "b".repeat(64), source_locator: "Precios!A8:F8",
      source_url: "https://www.dane.gov.co/weekly.xlsx",
      details: { period_type: "weekly", period_end: "2026-09-25", trend: "++", ...(statistic ? { price_statistic: statistic } : {}) },
    };
    await page.route("**/api/references?*", route => route.fulfill({ json: { reference: quote, history: [quote] } }));
    await page.goto(`/references/${quote.quote_key}`);
    await expect(page.getByTestId("current-product-price")).toHaveAttribute("data-price", String(quote.price));
    const card = page.locator(".product-price-header");
    await expect(card).toContainText("Rango:");
    await expect(card).toContainText("Precio mayorista semanal");
    await expect(card).toContainText("Período:");
    if (statistic === "published_mean") {
      await expect(card).toContainText("Precio medio publicado");
      await expect(card).not.toContainText("Punto medio calculado");
    } else if (statistic === "range_midpoint") {
      await expect(card).toContainText("Punto medio calculado");
      await expect(card).not.toContainText("Precio medio publicado");
    } else {
      await expect(card).not.toContainText("Punto medio calculado");
      await expect(card).not.toContainText("Precio medio publicado");
    }
    await page.getByText("Fuente y método del precio", { exact: true }).click();
    await expect(page.locator(".reference-metadata")).toContainText("Semanal");
    await expect(page.locator(".reference-metadata")).toContainText("Tendencia publicada");
    await expect(page.locator(".reference-metadata")).toContainText("++");
  });
}
