import { test, expect } from "@playwright/test";
import { resolve } from "node:path";
import type { CatalogProduct, UnifiedCatalog } from "../src/lib/catalog-types";
import {
  catalogHref,
  catalogIdentity,
  catalogMatches,
  catalogPriceNumber,
  catalogReturnTo,
  catalogSavedKey,
  catalogUnit,
} from "../src/lib/catalog-display";
import { officialMoney } from "../src/lib/official-types";

const product = (extra: Partial<CatalogProduct> = {}): CatalogProduct => ({
  id: "tomate-chonto",
  identity: "tomate-chonto",
  saved_key: "tomate-chonto",
  name: "Tomate chonto",
  category: "Verduras",
  image_key: "tomato",
  price: 3512.3667,
  previous_price: null,
  date: "2026-07-31",
  market_count: 3,
  unit: "kg",
  source: "DANE · SIPSA",
  period: "monthly",
  series: "monthly",
  href: "/product/tomate-chonto?series=monthly&presentation=Por+unidad+de+medida&units=1+kg",
  currency: "COP",
  basis: "Promedio mensual mayorista",
  market: "Colombia",
  map_supported: true,
  search_terms: [],
  kind: "product",
  ...extra,
});

test("catalog keeps official quote identities and old saved products separate", () => {
  const local = product();
  const quote = product({
    id: "reference:quote-a",
    identity: "reference:quote-a",
    saved_key: "reference:quote-a",
    kind: "official-reference",
    product_id: local.id,
  });
  expect(catalogSavedKey(local)).toBe("tomate-chonto");
  expect(catalogSavedKey(quote)).toBe("reference:quote-a");
  expect(catalogIdentity(quote)).not.toBe(catalogIdentity(local));
  expect(
    catalogPriceNumber(
      product({ price: 7.9735, currency: "USD", kind: "official-reference" }),
    ),
  ).toBe("7,9735");
});

test("named search accepts bounded rose and arabica aliases without rosado matches", () => {
  const rose = product({ name: "Rosa híbrida de té · Freedom / 50 cm" });
  const coffee = product({ name: "Café arábica · otros suaves ICO" });
  for (const query of ["Rosa", "Rosas", "Rose", "roses Freedom 50"])
    expect(catalogMatches(rose, query)).toBe(true);
  for (const query of ["Arabica", "Arábica", "Arábigo", "café arábico"])
    expect(catalogMatches(coffee, query)).toBe(true);
  expect(
    catalogMatches(product({ name: "Fríjol Uribe rosado" }), "Rosas"),
  ).toBe(false);
  expect(catalogMatches(rose, "Freedom 60")).toBe(false);
});

test("detail URLs retain exact selection and return to all catalog filters", () => {
  const back = catalogReturnTo("/products", "Mora", "Frutas", "COP");
  const row = product({
    href: "/product/mora?series=city&presentation=Caja+de+cart%C3%B3n&units=2.5+Kilogramo&region=Atl%C3%A1ntico",
  });
  const link = new URL(catalogHref(row, back), "https://example.test");
  expect(link.searchParams.get("presentation")).toBe("Caja de cartón");
  expect(link.searchParams.get("units")).toBe("2.5 Kilogramo");
  expect(link.searchParams.get("region")).toBe("Atlántico");
  expect(link.searchParams.get("returnTo")).toBe(back);
});

test.describe("unified catalog browser coverage", () => {
  let catalog: UnifiedCatalog;
  test.beforeAll(async ({ request }) => {
    const response = await request.get("/api/catalog", { timeout: 90000 });
    expect(response.ok()).toBe(true);
    catalog = await response.json();
    expect(catalog.products.length).toBeGreaterThan(24);
    expect(catalog.products.some((p) => p.kind === "official-reference")).toBe(
      true,
    );
  });
  test.beforeEach(async ({ page }) => {
    // Use the captured live API response for deterministic UI checks. Detail
    // pages below still read the actual source-backed API.
    await page.route("**/api/catalog*", (route) =>
      route.fulfill({ json: catalog }),
    );
  });

  test("one search finds arabica, cacao, roses and city quotes with exact price units", async ({
    page,
  }) => {
    await page.goto("/products");
    await expect(page.locator(".product-card").first()).toBeVisible();
    await expect(
      page.getByRole("link", {
        name: /otras fuentes oficiales|Informes por ciudades|Resumen del anexo/i,
      }),
    ).toHaveCount(0);
    for (const name of ["Departamento", "Categoría", "Moneda"])
      await expect(
        page.getByRole("combobox", { name, exact: true }),
      ).toBeVisible();
    const city = catalog.products.find((p) => p.series === "city")!;
    expect(city).toBeTruthy();
    for (const query of ["Arabica", "cacao", "Rosas", city.name]) {
      const search = page.getByRole("combobox", { name: "Buscar producto" });
      await search.fill(query);
      await search.press("Escape");
      const expected = catalog.products.filter((p) => catalogMatches(p, query));
      expect(expected.length).toBeGreaterThan(0);
      await expect(page.locator(".product-card")).toHaveCount(
        Math.min(24, expected.length),
      );
      for (const row of expected.slice(0, 3)) {
        const card = page.locator(`[data-catalog-identity="${row.identity}"]`);
        await expect(card.locator(".product-price")).toHaveAttribute(
          "data-price",
          String(row.price),
        );
        await expect(card.locator(".product-price")).toHaveAttribute(
          "data-currency",
          row.currency,
        );
        await expect(card.locator(".product-price")).toContainText(
          catalogUnit(row),
        );
        await expect(card).toContainText(row.basis);
        if (row.kind === "official-reference")
          await expect(card).toContainText(row.market);
        const href = new URL(
          (await card
            .getByRole("link", { name: "Ver producto", exact: true })
            .getAttribute("href"))!,
          "https://example.test",
        );
        const source = new URL(row.href, "https://example.test");
        expect(href.pathname).toBe(source.pathname);
        for (const [key, value] of source.searchParams)
          expect(href.searchParams.get(key)).toBe(value);
      }
    }
  });

  test("official detail and source access preserve the selected price and return filters", async ({
    page,
    request,
  }) => {
    test.setTimeout(120000);
    const row = catalog.products.find(
      (p) => p.product_id === "wb-coffee-arabica",
    )!;
    expect(row).toBeTruthy();
    await page.goto("/products?q=Ar%C3%A1bigo&category=Caf%C3%A9&currency=USD");
    const card = page.locator(`[data-catalog-identity="${row.identity}"]`);
    await expect(card).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Ver mapa", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("combobox", { name: "Buscar producto" }).click();
    await page.getByRole("option").first().click();
    await expect(page).toHaveURL(/\/references\//);
    const sourceResponse = await request.get(
      "/api/references?id=" + row.quote_key,
    );
    expect(sourceResponse.ok()).toBe(true);
    const { reference } = await sourceResponse.json();
    expect(reference.price).toBe(row.price);
    expect(reference.currency).toBe(row.currency);
    expect(reference.unit).toBe(row.unit);
    await expect(page.getByTestId("current-product-price")).toContainText(
      officialMoney(reference.price, reference.currency),
    );
    await expect(
      page.getByRole("link", { name: "Consultar fuente", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Consultar fuente", exact: true }),
    ).toHaveAttribute("href", new RegExp("/evidence/" + reference.document_id));
    await page.locator(".back-link").click();
    await expect(
      page.getByRole("combobox", { name: "Buscar producto" }),
    ).toHaveValue("Arábigo");
    await expect(
      page.getByRole("combobox", { name: "Categoría", exact: true }),
    ).toHaveValue("Café");
    await expect(
      page.getByRole("combobox", { name: "Moneda", exact: true }),
    ).toHaveValue("USD");
    await page.reload();
    await expect(
      page.getByRole("combobox", { name: "Buscar producto" }),
    ).toHaveValue("Arábigo");
    await expect(page.getByLabel("Filtros aplicados")).toContainText("USD");
  });

  test("legacy saved IDs and exact official saved keys survive reload together", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      if (!localStorage.getItem("agroamigo-preferences-v2"))
        localStorage.setItem(
          "agroamigo-preferences-v2",
          JSON.stringify({ region: "", saved: ["tomate-chonto"] }),
        );
    });
    const row = catalog.products.find(
      (p) => p.product_id === "wb-coffee-arabica",
    )!;
    await page.goto("/products?q=Arabica&currency=USD");
    const card = page.locator(`[data-catalog-identity="${row.identity}"]`);
    await card
      .getByRole("button", { name: "Guardar " + row.name, exact: true })
      .click();
    await page.goto("/saved");
    await expect(
      page.locator('[data-product-id="tomate-chonto"]'),
    ).toBeVisible();
    await expect(
      page.locator(`[data-catalog-identity="${row.identity}"]`),
    ).toBeVisible();
    await page.reload();
    await expect(page.locator(".product-card")).toHaveCount(2);
    const preferences = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("agroamigo-preferences-v2")!),
    );
    expect(preferences.saved).toEqual(
      expect.arrayContaining(["tomate-chonto", row.saved_key]),
    );
  });

  test("load-more and 320px cards keep currency, units and applied filters visible", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/products");
    await expect(page.locator(".product-card")).toHaveCount(24);
    await page.getByRole("button", { name: /Ver más productos/ }).click();
    await expect(page.locator(".product-card")).toHaveCount(48);
    await page.locator(".product-card").nth(20).scrollIntoViewIfNeeded();
    await expect(page.getByLabel("Filtros aplicados")).toBeVisible();
    const bounds = await page.evaluate(() => ({
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
      filters: document
        .querySelector('[aria-label="Filtros aplicados"]')!
        .getBoundingClientRect()
        .toJSON(),
      overflowingPrices: [
        ...document.querySelectorAll<HTMLElement>(".product-price"),
      ].filter((e) => e.scrollWidth > e.clientWidth + 1).length,
    }));
    expect(bounds.scroll).toBeLessThanOrEqual(bounds.width);
    expect(bounds.filters.top).toBeGreaterThanOrEqual(0);
    expect(bounds.filters.bottom).toBeLessThan(250);
    expect(bounds.overflowingPrices).toBe(0);
    await page.screenshot({
      path: resolve(
        __dirname,
        "../../../artifacts",
        `unified-catalog-${test.info().project.name}-320.png`,
      ),
    });
  });
});
