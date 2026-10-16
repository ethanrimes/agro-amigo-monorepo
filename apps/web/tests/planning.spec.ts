import { resolve } from "node:path";
import { test, expect, type Page } from "@playwright/test";
import {
  seasonalPrices,
  offerResult,
  weatherSignals,
} from "../src/lib/planning-math";

test("PDF text and page rendering work without stream async iterators on older iOS", async ({
  page,
}) => {
  await page.addInitScript(() => {
    delete (ReadableStream.prototype as unknown as Record<symbol, unknown>)[
      Symbol.asyncIterator
    ];
  });
  await page.goto("/evidence/coffee-cost-benchmark?page=6");
  await expect(page.locator('canvas[data-rendered="true"]')).toHaveAttribute(
    "aria-label",
    "Página 6 del PDF",
  );
  await expect(page.locator(".pdf-text")).toContainText("1,550,805");
  await page.getByRole("button", { name: "Siguiente →" }).click();
  await expect(page.locator('canvas[data-rendered="true"]')).toHaveAttribute(
    "aria-label",
    "Página 7 del PDF",
  );
});
test("PDF page search reaches the last page without changing the current page while typing", async ({ page }) => {
  await page.goto("/evidence/a39c2c8c89aa129f22161d3a39cae0ec761aa952c56c90e66c1551e034ca7c63?page=23");
  const pageChoice = page.getByRole("group", { name: "Página del documento" });
  await expect(pageChoice).toHaveAttribute("data-selected-value", "23");
  await expect(page.locator('canvas[data-rendered="true"]')).toHaveAttribute("aria-label", "Página 23 del PDF");
  await pageChoice.getByRole("combobox").fill("26");
  await expect(pageChoice).toHaveAttribute("data-selected-value", "23");
  await expect(pageChoice.getByRole("option")).toHaveCount(1);
  await expect(pageChoice.getByRole("option")).toContainText("26");
  await expect(pageChoice.getByRole("button", { name: "Quitar selección" })).toHaveCount(0);
  await pageChoice.getByRole("option").click();
  await expect(pageChoice).toHaveAttribute("data-selected-value", "26");
  await expect(page.locator('canvas[data-rendered="true"]')).toHaveAttribute("aria-label", "Página 26 del PDF");
});
const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
const profile = {
  municipalityId: "41551",
  name: "Prueba Pitalito",
  cropCode: "2030300",
  variety: "",
  area: "1",
  stage: "harvest",
  plantingDate: "",
  floweringDate: "2026-02-01",
  irrigation: false,
  latitude: "",
  longitude: "",
  elevation: "1800",
};
async function farm(page: Page) {
  await page.addInitScript((p) => {
    localStorage.setItem("agroamigo-farm-v1", JSON.stringify(p));
  }, profile);
}
test("municipal crop references remain available from the informational workspace", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      "agroamigo-location-v1",
      JSON.stringify({
        point: { latitude: 1.9, longitude: -76.1 },
        municipalityId: "41551",
        name: "Mi pin",
      }),
    ),
  );
  await page.goto("/farm");
  await page
    .getByRole("button", { name: "¿Qué se cultiva en este municipio?" })
    .click();
  await page.getByRole("combobox", { name: "Consultar cultivo reportado", exact: true }).fill("Café");
  await page.getByRole("option").filter({ hasText: "Café" }).first().click();
  await expect(page.locator(".crop-option").first()).toBeVisible();
  await expect(page.locator(".aptitude-result").first()).toBeVisible();
  await expect(
    page.locator(".crop-option .evidence-link").first(),
  ).toHaveAttribute("href", /municipality=41551/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("seasonal references use five complete years and crop cost templates link to original tables", async ({
  page,
  request,
}) => {
  const season = await (
    await request.get("/api/planning/seasonality?product=cafe-pergamino-seco")
  ).json();
  expect(season.years).toHaveLength(5);
  expect(season.years[0].reference_year).toBe(2021);
  expect(seasonalPrices(season, 12)?.samples).toBe(5);
  expect(
    seasonalPrices({ ...season, years: season.years.slice(0, 2) }, 12),
  ).toBeNull();
  await farm(page);
  await page.goto("/plan?tab=budget");
  await page
    .getByText("Consultar historia y estacionalidad de precios", {
      exact: true,
    })
    .click();
  await expect(page.locator(".seasonal-bars button")).toHaveCount(12);
  const picker = page.getByRole("combobox", { name: "Cultivo y sistema de referencia" });
  await picker.fill("Frijol");
  await page.getByRole("option", { name: /^Frijol ·/ }).first().click();
  await expect(page.getByRole("group", { name: "Cultivo y sistema de referencia" }))
    .toContainText("Seleccionado: Frijol");
  const study = page
    .locator(".published-cost-references details")
    .filter({ hasText: "región occidente (Huila)" })
    .first();
  await study.locator("summary").click();
  await expect(study).toContainText("nominales");
  await study
    .getByRole("link", { name: /Ver tabla original de costos/ })
    .click();
  await expect(page.locator("dialog")).toBeVisible();
  await expect(page.getByRole("group", { name: "Página del documento" })).toHaveAttribute("data-selected-value", "13");
  await expect(page.locator("canvas[data-rendered=true]")).toBeVisible({
    timeout: 35000,
  });
});

test("offers handle partial quantities, units, discounts, deadlines and buyer costs", async ({
  page,
}, info) => {
  await page.goto("/offers");
  await page.getByLabel("Cantidad total que comparas (kg)").fill("250");
  await page.getByLabel("Unidad de las cotizaciones").selectOption("125");
  await page.getByLabel("Precio oferta 1", { exact: true }).fill("2000000");
  await page.getByLabel("Kilos oferta 1", { exact: true }).fill("250");
  await page.getByLabel("Descuento oferta 1", { exact: true }).fill("5");
  await page.getByLabel("Transporte oferta 1", { exact: true }).fill("100000");
  await page.getByLabel("Precio oferta 2", { exact: true }).fill("2100000");
  await page.getByLabel("Kilos oferta 2", { exact: true }).fill("125");
  await expect(
    page.locator(".offer-result [data-result=sale]").first(),
  ).toHaveText(money(3700000));
  await expect(page.locator(".best-offer h2")).toHaveText("Oferta 2");
  await expect(page.locator(".offer-result").nth(1)).toContainText(
    "125 kg fuera de esta oferta",
  );
  await page
    .getByLabel("Vigencia oferta 2", { exact: true })
    .fill("2020-01-01");
  await expect(page.locator(".best-offer")).toHaveCount(0);
  await expect(
    page.locator(".offer-result [data-result=purchase]").first(),
  ).toHaveText(money(3900000));
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `offers-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.reload();
  await expect(page.getByLabel("Precio oferta 1", { exact: true })).toHaveValue(
    "2000000",
  );
});
test("price evidence renders PDF pages and preserves byte integrity", async ({
  page,
  request,
}, info) => {
  await page.goto("/product/tomate-chonto");
  const currentSource = page.getByRole("link", {
      name: /Consultar (?:fuente del precio actual|una de las fuentes del promedio)/,
    });
  const sourcePage = Number(new URL((await currentSource.getAttribute("href"))!, page.url()).searchParams.get("page"));
  expect(sourcePage).toBeGreaterThan(1);
  await currentSource.click();
  await expect(page.locator("canvas[data-rendered=true]")).toBeVisible({
    timeout: 35000,
  });
  await page.getByText("Leer el texto de esta página", { exact: true }).click();
  await expect(page.locator(".pdf-text")).toContainText("PRECIOS DE VENTA MAYORISTA");
  await expect(page.locator(".pdf-text")).toContainText("Tomate chonto");
  await expect(page.getByRole("group", { name: "Página del documento" })).toHaveAttribute("data-selected-value", String(sourcePage));
  await page.getByRole("button", { name: "← Anterior", exact: true }).click();
  await expect(page.getByRole("group", { name: "Página del documento" })).toHaveAttribute("data-selected-value", String(sourcePage - 1));
  await page.getByRole("button", { name: "Siguiente →", exact: true }).click();
  await expect(page.getByRole("group", { name: "Página del documento" })).toHaveAttribute("data-selected-value", String(sourcePage));
  await expect(page.locator("canvas[data-rendered=true]")).toBeVisible();
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `evidence-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  const download = await page
    .locator("dialog a[download]")
    .getAttribute("href");
  const id = download!.split("/api/evidence/")[1].split("/")[0];
  const meta = await (await request.get("/api/evidence/" + id)).json();
  const bytes = await (
    await request.get("/api/evidence/" + meta.id + "/content")
  ).body();
  const { createHash } = await import("node:crypto");
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(meta.id);
});
test("daily quotes and input prices retain their frequency, units and source", async ({
  page,
  request,
}) => {
  await page.goto("/daily");
  await page.getByRole("combobox", { name: "Buscar producto en el boletín", exact: true }).fill("Habichuela");
  await page.getByRole("option", { name: "Habichuela", exact: true }).click();
  const daily = await (await request.get("/api/planning/daily")).json();
  const quote = daily.find(
    (q: { product_name: string; market_name: string }) =>
      q.product_name === "Habichuela",
  );
  expect(quote).toBeTruthy();
  const plaza = page.getByRole("group", { name: "Plaza del boletín" });
  await plaza.getByRole("combobox").fill(quote.market_name);
  await plaza.getByRole("option", { name: quote.market_name, exact: true }).click();
  await expect(plaza).toHaveAttribute("data-selected-value", quote.market_name);
  await expect(page.locator(".input-card")).toHaveCount(1);
  expect(quote.price).toBeGreaterThan(0);
  await expect(page.locator(".input-price")).toContainText(money(quote.price));
  await page.goto("/insumos?department=Huila");
  await page.getByLabel("Buscar insumo", { exact: true }).fill("urea");
  await page.getByLabel("Buscar insumo", { exact: true }).press("Escape");
  await expect(page.locator(".input-catalog-card").first()).toBeVisible();
  await page.locator(".input-catalog-card").first().click();
  await page
    .getByRole("link", { name: "Comprobar precio", exact: true })
    .click();
  await expect(page.locator(".workbook-viewer")).toContainText("Excel · Solo lectura");
  expect(
    (await request.get("/api/planning/weather?lat=85&lon=10")).status(),
  ).toBe(400);
});
test("unavailable weather is actionable and never supplies invented forecasts", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      "agroamigo-location-v1",
      JSON.stringify({
        point: { latitude: 1.9, longitude: -76.1 },
        municipalityId: "41551",
        name: "Mi pin",
      }),
    ),
  );
  await page.route("**/api/planning/weather*", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "No pudimos consultar el clima." }),
    }),
  );
  await page.goto("/farm");
  await page.getByLabel("Horizonte de la información").selectOption("forecast");
  await expect(
    page.locator(".zone-reading [role=alert]").first(),
  ).toBeVisible();
  await expect(page.locator(".forecast-day-strip")).toHaveCount(0);
});
