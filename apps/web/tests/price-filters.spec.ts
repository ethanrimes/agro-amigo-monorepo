import { test, expect } from "@playwright/test";

test("rapid filter changes preserve the market while an earlier response is pending", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.route("**/api/products/mora-de-castilla?**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (query.get("market") && query.get("units") === "2.5 Kilogramo")
      await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.continue();
  });
  await page.goto(
    "/product/mora-de-castilla?series=city&presentation=Caja+de+cart%C3%B3n&units=2.5+Kilogramo",
  );
  const current = page.getByTestId("current-product-price");
  await expect(current).toContainText("21.000");
  await page
    .getByRole("combobox", { name: "Mercado", exact: true })
    .selectOption("sipsa-barranquilla-barranquillita");
  await page
    .getByRole("combobox", { name: "Unidades", exact: true })
    .selectOption("12.5 Kilogramo");
  await expect(current).toContainText("79.500");
  await expect(
    page.getByRole("combobox", { name: "Mercado", exact: true }),
  ).toHaveValue("sipsa-barranquilla-barranquillita");
  await expect(page.locator(".applied-filters").first()).toContainText(
    "Barranquillita",
  );
  await page
    .getByRole("button", { name: "Ver mapa", exact: true })
    .first()
    .click();
  await expect(page.locator(".colombia-map")).toHaveAttribute(
    "data-ready",
    "true",
  );
  await page.locator(".map-summary select").selectOption("Atlántico");
  await expect(page.locator(".map-popup-price")).toContainText("79.500");
  await expect
    .poll(async () =>
      page.locator(".maplibregl-popup-content").evaluate((el) => {
        const panel = el.getBoundingClientRect(),
          map = el.closest(".map-stage")!.getBoundingClientRect();
        return (
          panel.top >= map.top &&
          panel.bottom <= map.bottom &&
          panel.left >= map.left &&
          panel.right <= map.right
        );
      }),
    )
    .toBe(true);
  expect(
    await page
      .locator(".map-workspace > .applied-filters")
      .evaluate((el) => el.clientHeight >= el.scrollHeight),
  ).toBe(true);
});

test("comparison keeps matching-date choices without a period control", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.route("**/api/compare/markets?**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    if (q.get("dates") !== "same")
      await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.continue();
  });
  await page.goto(
    "/compare/markets?series=city&a=sipsa-barranquilla-barranquillita&product=mora-de-castilla&history=all",
  );
  await expect(
    page.locator('[aria-label="Resultado de la comparación"]'),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Fechas a comparar", exact: true })
    .selectOption("same");
  await expect(
    page.locator('[aria-label="Resultado de la comparación"]'),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Período de búsqueda", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Fechas a comparar", exact: true }),
  ).toHaveValue("same");
  await expect(page.locator(".applied-filters")).not.toContainText("Todo el histórico");
});
