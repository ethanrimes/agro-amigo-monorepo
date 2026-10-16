import { expect, test } from "@playwright/test";

for (const series of ["city", "monthly"]) {
  test(`opening a saved ${series} product query requests only its displayed filters`, async ({ page }) => {
    const filters = {
      region: "Bogotá, D.C.", series,
      market: "sipsa-bogota-d-c-corabastos",
      presentation: series === "city" ? "Bulto" : "Por unidad de medida",
      units: series === "city" ? "70 Kilogramo" : "1 kg",
      history: "all",
    };
    const queries: Record<string, string>[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/api/products/limon-tahiti")
        queries.push(Object.fromEntries(url.searchParams));
    });
    await page.route("**/api/products/limon-tahiti?**", (route) => route.fulfill({ json: {
      product: { id: "limon-tahiti", name: "Limón tahití", category: "Frutas", image_key: "lemon" },
      markets: [], history: [{ date: "2026-09-07", price: 190000, market_count: 1 }],
      current: { date: "2026-09-07", price: 190000, market_count: 1 },
      classification: [["Frutas", "Cítricos"]], filters,
      options: {
        series: ["city", "monthly"], presentations: [filters.presentation], units: [filters.units],
        markets: [{ id: filters.market, name: "Bogotá, D.C., Corabastos" }],
      },
    } }));

    await page.goto(`/product/limon-tahiti?${new URLSearchParams(filters)}`);
    await expect(page.getByTestId("current-product-price")).toContainText("190.000");
    await expect(page.getByRole("combobox", { name: "Tipo de precio", exact: true })).toHaveValue(series);
    await expect(page.locator(".applied-filters")).toContainText("Corabastos");
    await expect(page.locator(".applied-filters")).toContainText(filters.presentation);
    await expect(page.locator(".applied-filters")).toContainText(filters.units);
    await expect(page.locator(".applied-filters")).toContainText("Todo el historial");
    expect(queries).toEqual([filters]);
  });
}
