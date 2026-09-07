import { test, expect } from "@playwright/test";
const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
test("five destinations stay selected for their details and coffee lives in products", async ({
  page,
  isMobile,
}) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", {
    name: isMobile ? "Navegación móvil" : "Navegación principal",
    exact: true,
  });
  await expect(nav.getByRole("link")).toHaveText([
    "Inicio",
    "Productos",
    "Mercados",
    "Insumos",
    "Mi finca",
  ]);
  for (const [url, name] of [
    ["/product/cafe-pergamino-seco", "Productos"],
    ["/market/sipsa-bogota-d-c-corabastos", "Mercados"],
    ["/insumos", "Insumos"],
    ["/plan", "Mi finca"],
  ]) {
    await page.goto(url);
    await expect(page.locator("h1")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(nav.locator("[aria-current]")).toHaveCount(1);
    await expect(nav.getByRole("link", { name, exact: true })).toHaveAttribute(
      "aria-current",
      /page|location/,
    );
  }
});
test("search suggestions filter without accents, support keyboard selection, and clear", async ({
  page,
}) => {
  await page.goto("/products");
  await expect(page.locator(".product-card").first()).toBeVisible();
  const search = page.getByRole("combobox", {
    name: "Buscar producto",
    exact: true,
  });
  await search.fill("cafe");
  await expect(
    page
      .getByRole("listbox")
      .getByRole("option", { name: /Café pergamino seco/ }),
  ).toBeVisible();
  await search.fill("cafe pergamino");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(1);
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/product\/cafe-pergamino-seco$/);
  await expect(page.locator(".coffee-big-price")).toContainText(
    "/ carga de 125 kg",
  );
  await page.goto("/markets");
  const market = page.getByRole("combobox", {
    name: "Buscar mercado",
    exact: true,
  });
  await expect(page.locator(".market-card").first()).toBeVisible();
  await market.fill("corabastos");
  await page.getByRole("listbox").getByRole("option").click();
  await expect(page).toHaveURL(/\/market\/sipsa-bogota-d-c-corabastos$/);
});
test("product and market supply have dated volumes, month selection and original records", async ({
  page,
  request,
}) => {
  await page.goto("/product/aguacate-hass");
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await expect(page.locator(".supply-summary")).toContainText("toneladas");
  const data = await (
    await request.get("/api/explore/supply?product=aguacate-hass")
  ).json();
  expect(data.rows.length).toBeGreaterThan(0);
  expect(data.history.length).toBeGreaterThanOrEqual(10);
  await page
    .getByLabel("Mes de consulta")
    .selectOption(data.history.at(-2).date);
  await expect(
    page.locator(".supply-bars button[aria-pressed=true]"),
  ).toHaveAttribute("aria-label", /toneladas/);
  await page.getByRole("link", { name: "Comprobar cantidad" }).first().click();
  await expect(page.locator("dialog .evidence-records")).toContainText(
    "Cantidad (kg)",
  );
  await expect(page.locator("dialog .evidence-records")).toContainText(
    "Registros en el archivo",
  );
  await page.getByRole("button", { name: "Cerrar ventana" }).click();
  await page.goto("/market/sipsa-bogota-d-c-corabastos");
  await expect(
    page.locator(".entity-price-list article").first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await expect(page.locator(".supply-list article").first()).toBeVisible();
  await expect(page.locator(".supply-content")).toContainText(
    "no existencias disponibles",
  );
});
test("input details preserve presentation, department prices and honest supply coverage", async ({
  page,
  request,
}) => {
  await page.goto("/insumos");
  await expect(page.locator(".input-catalog-card").first()).toBeVisible();
  const search = page.getByRole("combobox", {
    name: "Buscar insumo",
    exact: true,
  });
  await search.fill("urea");
  await expect(
    page.getByRole("listbox").getByRole("option").first(),
  ).toContainText(/Urea/i);
  await page.getByRole("listbox").getByRole("option").first().click();
  await expect(page.locator(".input-detail-summary")).toBeVisible();
  const id = new URL(page.url()).pathname.split("/").at(-1)!;
  const data = await (await request.get("/api/explore/input?id=" + id)).json();
  await expect(page.locator(".entity-hero")).toContainText(
    data.input.presentation,
  );
  await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "No hay datos de existencias de este insumo",
    }),
  ).toBeVisible();
  await expect(page.locator(".coverage-tags span")).toHaveCount(
    data.regions.length,
  );
  await page.getByRole("tab", { name: "Precios", exact: true }).click();
  await page
    .getByRole("link", { name: "Comprobar precio", exact: true })
    .click();
  await expect(page.locator("dialog .evidence-records")).toContainText(
    data.input.presentation,
  );
});
test("reader opens over the current page, supports zoom, download, escape and back", async ({
  page,
}) => {
  await page.goto("/product/tomate-chonto");
  const source = page.getByRole("link", {
    name: "Comprobar precios en el documento",
    exact: true,
  });
  await source.scrollIntoViewIfNeeded();
  const url = page.url();
  await source.click();
  await expect(page.locator("dialog")).toBeVisible();
  await expect(page).toHaveURL(url);
  await expect(
    page.locator("dialog .pdf-paper canvas[data-rendered=true]"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Siguiente →", exact: true }).click();
  await expect(page.getByLabel("Página del documento")).toHaveValue("2");
  await page.getByLabel("Tamaño del documento").selectOption("1.5");
  await expect(
    page.locator("dialog .pdf-paper canvas[data-rendered=true]"),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.locator("dialog a[download]").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  await page.keyboard.press("Escape");
  await expect(page.locator("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(url);
  await expect(source).toBeFocused();
  await source.click();
  await expect(page.locator("dialog")).toBeVisible();
  await page.goBack();
  await expect(page.locator("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(url);
});
test("catalog maps load real Colombia boundaries and filtered references", async ({
  page,
  browserName,
}) => {
  await page.goto("/products");
  await expect(page.locator(".product-card").first()).toBeVisible();
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  await expect(page.locator(".colombia-map")).toHaveAttribute(
    "data-ready",
    "true",
    { timeout: 45000 },
  );
  await expect(
    page.locator(".map-reference-list article").first(),
  ).toBeVisible();
  await expect(page.locator(".colombia-map")).toHaveAttribute(
    "data-features",
    /^[1-9][0-9]*$/,
  );
  const picker = page.getByRole("combobox", {
    name: "Elegir producto en el mapa",
  });
  await picker.fill("tomate chonto");
  await page
    .getByRole("option", { name: "Tomate chonto", exact: true })
    .click();
  await expect(
    page.locator(".map-reference-list article").first(),
  ).toBeVisible();
  await page
    .locator("dialog")
    .getByRole("tab", { name: "Abastecimiento", exact: true })
    .click();
  await expect(page.locator(".map-results")).toContainText(
    "Llegadas reportadas",
  );
  await expect(
    page.locator(".map-reference-list article").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cerrar ventana" }).click();
  await expect(page.locator("dialog")).toHaveCount(0);
  for (const path of ["/markets", "/insumos"]) {
    await page.goto(path);
    await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
    await expect(page.locator(".colombia-map")).toHaveAttribute(
      "data-ready",
      "true",
    );
    await expect(
      page.locator(".map-reference-list article").first(),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cerrar ventana" }).click();
  }
});
