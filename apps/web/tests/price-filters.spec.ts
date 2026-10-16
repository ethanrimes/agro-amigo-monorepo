import { test, expect } from "@playwright/test";
import { latestMoraPackages } from "./helpers/mora-source";
import { money } from "../src/lib/market-types";

test("rapid filter changes preserve the market while an earlier response is pending", async ({
  page, request,
}) => {
  test.setTimeout(90_000);
  const originals = await latestMoraPackages(request);
  const largePrice = money(originals.get("12.5 Kilogramo")!.price);
  const initialResponse = await request.get("/api/products/mora-de-castilla?series=city&presentation=Caja+de+cart%C3%B3n&units=2.5+Kilogramo");
  expect(initialResponse.ok()).toBeTruthy();
  const initial = await initialResponse.json();
  const latestMarkets = initial.markets.filter((row: { date: string }) => row.date === initial.current.date);
  expect(latestMarkets.length).toBeGreaterThan(0);
  expect(initial.current.price).toBeCloseTo(latestMarkets.reduce((sum: number, row: { price: number }) => sum + row.price, 0) / latestMarkets.length, 8);
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
  await expect(current).toContainText(money(initial.current.price));
  const marketChoice = page.getByRole("group", { name: "Mercado", exact: true });
  await marketChoice.getByRole("combobox").fill("Barranquillita");
  await marketChoice.getByRole("option", { name: /Barranquillita/ }).click();
  const unitsChoice = page.getByRole("group", { name: "Unidades", exact: true });
  await unitsChoice.getByRole("combobox").fill("12.5 Kilogramo");
  await unitsChoice.getByRole("option", { name: "12.5 Kilogramo", exact: true }).click();
  await expect(current).toContainText(largePrice);
  await expect(marketChoice).toContainText(/Seleccionado: .*Barranquillita/);
  await marketChoice.getByRole("combobox").fill("Cali");
  await expect(page.locator(".applied-filters").first()).toContainText("Barranquillita");
  await expect(current).toContainText(largePrice);
  await marketChoice.getByRole("button", { name: "Borrar mercado" }).click();
  await expect(marketChoice).toContainText(/Seleccionado: .*Barranquillita/);
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
  const mapRegion = page.getByRole("group", { name: "Abrir precios de un departamento" });
  await mapRegion.getByRole("combobox").fill("Atlántico");
  await mapRegion.getByRole("option", { name: "Atlántico", exact: true }).click();
  await expect(page.locator(".map-popup-price")).toContainText(largePrice);
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
