import { resolve } from "node:path";
import { test, expect } from "@playwright/test";
const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
test("home has working prices, readable mobile layout, and no application errors", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.locator(".product-card")).toHaveCount(4);
  await expect(
    page.getByRole("heading", { name: "El campo, a tu alcance." }),
  ).toBeVisible();
  await expect(page.locator(".product-card").first()).toContainText(
    "/ carga de 125 kg",
  );
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  expect(errors).toEqual([]);
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `home-${info.project.name}.png`,
    ),
    fullPage: true,
  });
});
test("search, category filters, department, and saved products work", async ({
  page,
}) => {
  await page.goto("/products");
  await expect(page.locator(".product-card").first()).toBeVisible();
  await page
    .getByRole("combobox", { name: "Buscar producto", exact: true })
    .fill("aguacate");
  await page
    .getByRole("combobox", { name: "Buscar producto", exact: true })
    .press("Escape");
  await expect(page.locator(".product-card").first()).toContainText(
    /Aguacate/i,
  );
  const card = page.locator(".product-card").first();
  const name = await card.locator(".product-name").innerText();
  await card.getByRole("button", { name: /Guardar/ }).click();
  await page.goto("/saved");
  await expect(page.locator(".product-name")).toHaveText(name);
  await page.reload();
  await expect(page.locator(".product-name")).toHaveText(name);
  await page
    .locator(".product-card")
    .getByRole("button", { name: /Quitar/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Guarda lo que te interesa" }),
  ).toBeVisible();
  await page.goto("/products");
  await page
    .getByLabel("Departamento", { exact: true })
    .last()
    .selectOption("Antioquia");
  await expect(page.locator(".results-label")).toContainText("Antioquia");
  await page.getByRole("button", { name: "Frutas", exact: true }).click();
  await expect(page.locator(".product-category").first()).toHaveText("Frutas");
});
test("one shared experience ignores the retired role and shows selling and buying totals", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() =>
    localStorage.setItem(
      "agroamigo-preferences-v2",
      JSON.stringify({ role: "buyer", saved: [] }),
    ),
  );
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Soy comprador|Soy productor/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", {
      name: "El campo, a tu alcance.",
    }),
  ).toBeVisible();
  await page
    .locator(".product-name")
    .filter({ hasText: "Aguacate Hass" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Calcula el valor con transporte" }),
  ).toBeVisible();
  await page.getByLabel("Cantidad en kilos").fill("100");
  await page.getByLabel("Transporte total (COP)").fill("50000");
  const selected = await page.getByLabel("Mercado de referencia").inputValue();
  const data = await (
    await page.request.get("/api/products/" + page.url().split("/").at(-1))
  ).json();
  const price = data.markets.find((m: any) => m.id === selected).price;
  await expect(
    page.locator(".calculation-result [data-result=purchase]"),
  ).toHaveText(money(price * 100 + 50000));
  await expect(
    page.locator(".calculation-result [data-result=sale]"),
  ).toHaveText(money(price * 100 - 50000));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Calcula el valor con transporte" }),
  ).toBeVisible();
  const text = await page.locator(".market-value strong").allTextContents();
  expect(text.length).toBeGreaterThan(0);
});
test("coffee units and a buyer quote produce the correct net estimate", async ({
  page,
}, info) => {
  await page.goto("/coffee");
  await expect(
    page.getByRole("heading", { name: "¿Cuánto vale tu café?" }),
  ).toBeVisible();
  await page.getByLabel("Cantidad", { exact: true }).fill("125");
  await page.getByLabel("Unidad", { exact: true }).selectOption("1");
  await page.getByLabel("Oferta del comprador por carga (COP)").fill("2100000");
  await page.getByLabel("Transporte y descuentos totales (COP)").fill("50000");
  await expect(page.locator(".calculation-result>strong")).toHaveText(
    money(2050000),
  );
  await page.getByLabel("Cantidad", { exact: true }).fill("10");
  await page.getByLabel("Unidad", { exact: true }).selectOption("12.5");
  await expect(page.locator(".calculation-result>strong")).toHaveText(
    money(2050000),
  );
  await page.getByLabel("Cantidad", { exact: true }).fill("-1");
  await expect(page.locator(".invalid-input")).toBeVisible();
  await expect(page.locator(".calculation-result>strong")).toHaveText("—");
  await page.getByLabel("Cantidad", { exact: true }).fill("10");
  await page.getByRole("button", { name: "3 meses", exact: true }).click();
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  await expect(page.locator(".chart-data table")).toBeVisible();
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: resolve(
      __dirname,
      "../../../artifacts",
      `coffee-${info.project.name}.png`,
    ),
    fullPage: true,
  });
});
test("failed data requests show a retry and recover", async ({ page }) => {
  await page.route("**/api/catalog*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Prueba de conexión interrumpida." }),
    }),
  );
  await page.goto("/products");
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "No pudimos cargar los datos",
  );
  await page.unroute("**/api/catalog*");
  await page.getByRole("button", { name: "Volver a intentar" }).click();
  await expect(page.locator(".product-card").first()).toBeVisible();
});
test("legacy routes have a useful destination and source explanations are available", async ({
  page,
}) => {
  await page.goto("/markets");
  await expect(page.locator(".market-card").first()).toBeVisible();
  await page.goto("/insumos");
  await expect(
    page.getByRole("heading", { name: "Insumos agrícolas" }),
  ).toBeVisible();
  await page.goto("/sources");
  await page
    .getByText("¿Este es el precio que me van a pagar?", { exact: true })
    .click();
  await expect(
    page.getByText(/El valor final depende de la calidad/),
  ).toBeVisible();
  expect(await page.locator(".source-card a").count()).toBeGreaterThanOrEqual(
    14,
  );
});
