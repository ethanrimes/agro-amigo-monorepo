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
test("profile saves, local crop references and weather have working evidence", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/farm");
  await page
    .getByRole("button", { name: "Explorar ejemplo en Pitalito" })
    .click();
  await page.getByRole("tab", { name: "Clima y labores", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Tu plan para esta semana" }),
  ).toBeVisible();
  await expect(page.locator(".weather-day")).toHaveCount(7, { timeout: 35000 });
  await page.locator(".task-toggle").first().click();
  await expect(page.locator(".task-toggle").first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `farm-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.reload();
  await page.getByRole("tab", { name: "Clima y labores", exact: true }).click();
  await expect(page.locator(".task-toggle").first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.goto("/plan");
  await expect(page.locator(".crop-option").first()).toBeVisible();
  await expect(page.locator(".aptitude-result").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `plan-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
test("budget computes costs, commission and scenarios and preserves evidence", async ({
  page,
}, info) => {
  await farm(page);
  await page.goto("/plan?tab=budget");
  await expect(
    page.getByLabel("Cosecha de referencia (kg por hectárea)"),
  ).toBeVisible();
  await page.getByLabel("Área (hectáreas)", { exact: true }).fill("2");
  await page.getByLabel("Cosecha de referencia (kg por hectárea)").fill("1000");
  await page.getByLabel("Pérdida o producto no vendible (%)").fill("10");
  for (const [label, value] of [
    ["Preparación, siembra y labores por hectárea", "200000"],
    ["Semilla e insumos por hectárea", "300000"],
    ["Cosecha y poscosecha por hectárea", "100000"],
    ["Otros costos de producción por hectárea", "0"],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByRole("button", { name: "Ingresar mi precio", exact: true })
    .click();
  await page.getByLabel("Precio que recibirías por kg (COP)").fill("2000");
  await page
    .getByLabel("Gastos adicionales de venta, total (COP)")
    .fill("100000");
  await page.getByLabel("Comisión sobre la venta (%)").fill("10");
  await expect(page.locator(".break-even strong")).toContainText(
    money(1300000 / (1800 * 0.9)),
  );
  await expect(page.locator(".earnings-scenarios .typical strong")).toHaveText(
    money(1940000),
  );
  await page
    .getByRole("button", { name: "Guardar escenario", exact: true })
    .click();
  await expect(page.locator(".saved-scenarios")).toContainText(money(1940000));
  const saved = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("agroamigo-scenarios-legacy-farm") || "[]"),
  );
  expect(saved[0].sourceDocuments[0]).toMatch(/^[a-f0-9]{64}$/);
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `budget-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.getByLabel("Cosecha de referencia (kg por hectárea)").fill("0");
  await expect(
    page.getByRole("button", { name: "Guardar escenario", exact: true }),
  ).toBeDisabled();
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
  await expect(page.locator(".seasonal-bars button")).toHaveCount(12);
  await page
    .getByLabel("Cultivo y sistema del escenario")
    .selectOption({ label: "Frijol" });
  await page
    .getByLabel("Comenzar con una referencia publicada")
    .selectOption("frijol-2023-13");
  await expect(page.locator(".cost-reference")).toContainText("2023");
  await page
    .getByRole("link", { name: "Ver tabla original de costos" })
    .click();
  await expect(page).toHaveURL(/\/plan\?tab=budget$/);
  await expect(page.locator("dialog")).toBeVisible();
  await expect(page.getByLabel("Página del documento")).toHaveValue("13");
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
  await page
    .getByRole("link", {
      name: "Comprobar precios en el documento",
      exact: true,
    })
    .click();
  await expect(page.locator("canvas[data-rendered=true]")).toBeVisible({
    timeout: 35000,
  });
  await page.getByText("Leer el texto de esta página", { exact: true }).click();
  await expect(page.locator(".pdf-text")).toContainText("EXTRACTO GENERADO");
  await page.getByRole("button", { name: "Siguiente →", exact: true }).click();
  await expect(page.getByLabel("Página del documento")).toHaveValue("2");
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
  await page.getByLabel("Buscar producto en el boletín").fill("Habichuela");
  await page
    .getByLabel("Plaza del boletín")
    .selectOption("Montería, Mercado del Sur");
  await expect(page.locator(".input-card")).toHaveCount(1);
  const daily = await (await request.get("/api/planning/daily")).json();
  const quote = daily.find(
    (q: { product_name: string; market_name: string }) =>
      q.product_name === "Habichuela" &&
      q.market_name === "Montería, Mercado del Sur",
  );
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
  await expect(page.locator(".evidence-records")).toContainText(
    "Ubicación del dato",
  );
  expect(
    (await request.get("/api/planning/weather?lat=85&lon=10")).status(),
  ).toBe(400);
});
test("unavailable weather is actionable and never supplies invented forecasts", async ({
  page,
}) => {
  await farm(page);
  await page.route("**/api/planning/weather*", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "No pudimos consultar el clima." }),
    }),
  );
  await page.goto("/farm/legacy-farm");
  await page.getByRole("tab", { name: "Clima y labores", exact: true }).click();
  await expect(page.locator("main [role=alert]")).toBeVisible();
  await expect(page.locator(".weather-day")).toHaveCount(0);
});
