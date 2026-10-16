import { expect, test } from "@playwright/test";

const oldDocument = "a".repeat(64);
const newDocument = "b".repeat(64);
const product = { id: "limon-tahiti", name: "Limón Tahití", category: "Frutas", image_key: "produce" };
const allOptions = [
  { series: "city", market_id: "cucuta", market_name: "Cúcuta, Cenabastos",
    presentation: "Kilogramo", units: "1 Kilogramo",
    first_report_on: "2020-03-25", last_report_on: "2026-08-01" },
  { series: "city", market_id: "monteria", market_name: "MONTERIA, Mercado del Sur",
    presentation: "Bulto", units: "70 Kilogramo",
    first_report_on: "2020-03-25", last_report_on: "2026-08-01" },
  { series: "city", market_id: "monteria", market_name: "MONTERIA, Mercado del Sur",
    presentation: "Kilogramo", units: "2 Kilogramo",
    first_report_on: "2020-03-25", last_report_on: "2026-08-01" },
];
function detail(presentation: string, market: string, region = "") {
  const bulto = presentation === "Bulto";
  const units = bulto ? "70 Kilogramo" : "1 Kilogramo";
  const id = bulto ? "monteria" : "cucuta";
  const marketName = bulto ? "Montería, Mercado del Sur" : "Cúcuta, Cenabastos";
  const price = bulto ? 237_500 : 5_000;
  const document_id = bulto ? newDocument : oldDocument;
  const date = bulto ? "2020-03-25" : "2020-03-26";
  const point = { date, price, market_count: 1, sources: [{ document_id,
    source_locator: "PDF page 1, row 7, round 1", source_page: 1,
    market_id: id, market_name: marketName, source_units: units }] };
  return { product, markets: [{ id, name: marketName, city: "", region: bulto ? "Córdoba" : "Norte de Santander",
    price, min_price: price, max_price: price, date, document_id,
    source_locator: "PDF page 1, row 7, round 1", source_page: 1,
    product_id: product.id, source_url: `https://www.dane.gov.co/${document_id}.pdf`,
    period: "daily", series: "city", unit: "package", units, presentation }],
    history: [point], current: point, classification: [["Frutas", "Cítricos"]],
    additional_references: [],
    filters: { region, series: "city", market, presentation, units, history: "all" },
    options: { series: ["city"], presentations: ["Kilogramo", "Bulto"],
      units: bulto ? [units] : ["1 Kilogramo", "2 Kilogramo"],
      markets: [{ id, name: marketName, literal_name: marketName,
        first_report_on: "2020-03-25", last_report_on: "2026-08-01" }] },
    option_dimensions: { product_id: product.id, region, options: allOptions },
  };
}

test("failed Bulto request retains qualified Montería choice without old Cúcuta price or evidence", async ({ page }) => {
  const queries: Record<string, string>[] = [];
  await page.route("**/api/products/limon-tahiti?**", (route) => {
    const q = new URL(route.request().url()).searchParams;
    queries.push(Object.fromEntries(q));
    const presentation = q.get("presentation") || "Kilogramo";
    const market = q.get("market") || "";
    if (presentation === "Bulto" && !market)
      return route.fulfill({ status: 503, json: { error: "Fallo simulado de precio nuevo" } });
    return route.fulfill({ json: detail(presentation, market) });
  });
  await page.goto("/product/limon-tahiti?series=city&market=cucuta&presentation=Kilogramo&units=1+Kilogramo&history=all");
  const current = page.getByTestId("current-product-price");
  await expect(current).toContainText("5.000");
  await expect(page.getByRole("note").filter({ hasText: "Los mercados disponibles dependen" }))
    .toContainText("cambia la presentación o las unidades");
  await expect(page.getByRole("link", { name: "Consultar fuente del precio actual" })).toHaveAttribute("href", new RegExp(oldDocument));
  const presentation = page.getByRole("group", { name: "Presentación", exact: true });
  await presentation.getByRole("combobox").fill("Bulto");
  await presentation.getByRole("option", { name: "Bulto", exact: true }).click();
  await expect(page.locator(".empty-state[role='alert']")).toContainText("Fallo simulado de precio nuevo");
  await expect(current).toHaveText("Sin reporte");
  await expect(page.getByRole("group", { name: "Unidades", exact: true }))
    .toHaveAttribute("data-selected-value", "70 Kilogramo");
  await expect(page.locator(".applied-filters")).toContainText("Bulto");
  await expect(page.locator(".applied-filters")).toContainText("70 Kilogramo");
  await expect(page.locator(".applied-filters")).not.toContainText("Cúcuta");
  await expect(page.getByRole("link", { name: "Consultar fuente del precio actual" })).toHaveCount(0);
  await expect(page.locator(`a[href*="${oldDocument}"]`)).toHaveCount(0);
  const visibleQuery = new URL(page.url()).searchParams;
  expect(visibleQuery.get("presentation")).toBe("Bulto");
  expect(visibleQuery.get("units")).toBe("70 Kilogramo");
  const markets = page.getByRole("group", { name: "Mercado", exact: true });
  await markets.getByRole("combobox").fill("MONTERIA");
  await markets.getByRole("option", { name: /Montería, Mercado del Sur/ }).click();
  await expect(current).toContainText("237.500");
  await expect(markets).toHaveAttribute("data-selected-value", "monteria");
  await expect(page.getByRole("link", { name: "Consultar fuente del precio actual" })).toHaveAttribute("href", new RegExp(newDocument));
  expect(queries.some((query) => query.presentation === "Bulto" && query.market === "monteria")).toBe(true);
});

test("a previous department cannot restore its choices or price after a failed regional request", async ({ page }) => {
  await page.route("**/api/products/limon-tahiti?**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    const region = q.get("region") || "";
    if (region === "Norte de Santander")
      return route.fulfill({ json: detail("Kilogramo", "cucuta", region) });
    await new Promise((resolve) => setTimeout(resolve, 350));
    return route.fulfill({ status: 503, json: { error: "Sin respuesta para nuevo departamento" } });
  });
  await page.goto("/product/limon-tahiti?region=Norte+de+Santander&series=city&market=cucuta&presentation=Kilogramo&units=1+Kilogramo&history=all");
  await expect(page.getByTestId("current-product-price")).toContainText("5.000");
  await page.getByRole("button", { name: "Quitar filtro Departamento" }).click();
  await expect(page.locator(".empty-state[role='alert']")).toContainText("Sin respuesta para nuevo departamento");
  const applied = page.locator(".applied-filters");
  await expect(applied).toBeVisible();
  for (const current of ["Departamento: Colombia", "Fuente: Informe por ciudad · diario",
    "Mercado: Mercado seleccionado · por verificar", "Presentación: Kilogramo",
    "Unidades: 1 Kilogramo", "Moneda: COP · pesos colombianos",
    "Período: Todo el historial"])
    await expect(applied).toContainText(current);
  await expect(applied).not.toContainText("Cúcuta, Cenabastos");
  await expect(page.getByTestId("current-product-price")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Mercado", exact: true })).toHaveCount(0);
  await expect(page.locator(`a[href*="${oldDocument}"]`)).toHaveCount(0);
});

test("changing units clears a market that has no source for those units", async ({ page }) => {
  await page.route("**/api/products/limon-tahiti?**", (route) => {
    const q = new URL(route.request().url()).searchParams;
    if (q.get("units") === "2 Kilogramo")
      return route.fulfill({ status: 503, json: { error: "Precio nuevo no disponible" } });
    return route.fulfill({ json: detail("Kilogramo", "cucuta") });
  });
  await page.goto("/product/limon-tahiti?series=city&market=cucuta&presentation=Kilogramo&units=1+Kilogramo&history=all");
  await expect(page.getByTestId("current-product-price")).toContainText("5.000");
  const units = page.getByRole("group", { name: "Unidades", exact: true });
  await units.getByRole("combobox").fill("2 Kilogramo");
  await units.getByRole("option", { name: "2 Kilogramo", exact: true }).click();
  await expect(page.locator(".empty-state[role='alert']")).toContainText("Precio nuevo no disponible");
  await expect(page.getByRole("group", { name: "Mercado", exact: true }))
    .toHaveAttribute("data-selected-value", "");
  await expect(units).toHaveAttribute("data-selected-value", "2 Kilogramo");
  await expect(page.getByTestId("current-product-price")).toHaveText("Sin reporte");
  await expect(page.locator(`a[href*="${oldDocument}"]`)).toHaveCount(0);
});

test("a delayed failed package request cannot overwrite the later selected package", async ({ page }) => {
  await page.route("**/api/products/limon-tahiti?**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    if (q.get("presentation") === "Bulto") {
      await new Promise((resolve) => setTimeout(resolve, 900));
      await route.fulfill({ status: 503, json: { error: "Respuesta anterior tardía" } }).catch(() => {});
      return;
    }
    await route.fulfill({ json: detail("Kilogramo", "cucuta") });
  });
  await page.goto("/product/limon-tahiti?series=city&market=cucuta&presentation=Kilogramo&units=1+Kilogramo&history=all");
  const current = page.getByTestId("current-product-price");
  await expect(current).toContainText("5.000");
  const presentations = page.getByRole("group", { name: "Presentación", exact: true });
  await presentations.getByRole("combobox").fill("Bulto");
  await presentations.getByRole("option", { name: "Bulto", exact: true }).click();
  await expect(page.getByRole("group", { name: "Unidades", exact: true }))
    .toHaveAttribute("data-selected-value", "70 Kilogramo");
  await presentations.getByRole("combobox").fill("Kilogramo");
  await presentations.getByRole("option", { name: "Kilogramo", exact: true }).click();
  await expect(current).toContainText("5.000");
  await page.waitForTimeout(1000);
  await expect(current).toContainText("5.000");
  await expect(page.locator(".empty-state[role='alert']")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Consultar fuente del precio actual" }))
    .toHaveAttribute("href", new RegExp(oldDocument));
});

test("missing city package chooses the newest report during a failed request without hiding old units", async ({ page }) => {
  const options = [
    { series: "monthly", market_id: "monthly", market_name: "Colombia",
      presentation: "Por unidad de medida", units: "1 kg" },
    { series: "city", market_id: "old-market", market_name: "Mercado antiguo",
      presentation: "Bulto", units: "69 Kilogramo",
      first_report_on: "2021-01-01", last_report_on: "2021-11-01" },
    { series: "city", market_id: "current-market", market_name: "Mercado actual",
      presentation: "Bulto", units: "70 Kilogramo",
      first_report_on: "2026-10-06", last_report_on: "2026-10-06" },
  ];
  const cityRequests: Record<string, string>[] = [];
  await page.route("**/api/products/limon-tahiti?**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    if (q.get("series") === "city") {
      cityRequests.push(Object.fromEntries(q));
      await new Promise((resolve) => setTimeout(resolve, 250));
      return route.fulfill({ status: 503, json: { error: "Consulta de ciudad no disponible" } });
    }
    return route.fulfill({ json: {
      product, markets: [],
      history: [{ date: "2026-09-30", price: 100, market_count: 1 }],
      current: { date: "2026-09-30", price: 100, market_count: 1 },
      classification: [["Frutas", "Cítricos"]], additional_references: [],
      filters: { region: "", series: "monthly", market: "",
        presentation: "Por unidad de medida", units: "1 kg", history: "recent" },
      options: { series: ["city", "monthly"], presentations: ["Por unidad de medida"],
        units: ["1 kg"], markets: [] },
      option_dimensions: { product_id: product.id, region: "", options },
    } });
  });
  await page.goto("/product/limon-tahiti?series=monthly&presentation=Por+unidad+de+medida&units=1+kg");
  const price = page.getByTestId("current-product-price");
  await expect(price).toContainText("100");
  await page.getByRole("combobox", { name: "Tipo de precio", exact: true }).selectOption("city");
  const units = page.getByRole("group", { name: "Unidades", exact: true });
  await expect(units).toHaveAttribute("data-selected-value", "70 Kilogramo");
  await expect(page).toHaveURL(/[?&]units=70(?:\+|%20)Kilogramo/);
  await expect(page.locator(".empty-state[role='alert']"))
    .toContainText("Consulta de ciudad no disponible");
  await expect(price).toHaveText("Sin reporte");
  await units.getByRole("combobox").fill("69 Kilogramo");
  await units.getByRole("option", { name: "69 Kilogramo", exact: true }).click();
  await expect(page.locator(".empty-state[role='alert']"))
    .toContainText("Consulta de ciudad no disponible");
  await expect(units).toHaveAttribute("data-selected-value", "69 Kilogramo");
  const markets = page.getByRole("group", { name: "Mercado", exact: true });
  await markets.getByRole("combobox").fill("Mercado antiguo");
  await markets.getByRole("option", { name: /^Mercado antiguo(?:\s|$)/ }).click();
  await expect(page.locator(".empty-state[role='alert']"))
    .toContainText("Consulta de ciudad no disponible");
  await expect(markets).toHaveAttribute("data-selected-value", "old-market");
  await expect(units).toHaveAttribute("data-selected-value", "69 Kilogramo");
  await expect(price).toHaveText("Sin reporte");
  await expect(page.getByRole("link", { name: "Consultar fuente del precio actual" })).toHaveCount(0);
  expect(cityRequests.some((q) => q.presentation === "" && q.units === "")).toBe(true);
  expect(cityRequests.some((q) => q.units === "69 Kilogramo" && q.market === "old-market")).toBe(true);
});
