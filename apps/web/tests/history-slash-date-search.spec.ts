import { expect, test } from "@playwright/test";

const day = (n: number) => `2021-08-${String(n).padStart(2, "0")}`;
const documentId = (n: number) => String(n).padStart(64, "0");

test("city history slash, ISO and Spanish searches select the same dated own original", async ({ page }) => {
  const history = Array.from({ length: 26 }, (_, index) => {
    const n = index + 1;
    return {
      date: day(n), price: 70000 + n, market_count: 1,
      sources: [{ document_id: documentId(n), source_locator: `PDF page ${n},row 1`,
        source_page: n, market_id: "sipsa-bogota-corabastos", market_name: "Bogotá, D.C., Corabastos" }],
    };
  });
  await page.route("**/api/products/fixture-slash-city?**", (route) => route.fulfill({ json: {
    product: { id: "fixture-slash-city", name: "Tomate de árbol", category: "Frutas", image_key: "produce" },
    markets: [], classification: [["Frutas"]], additional_references: [], history, current: history.at(-1),
    filters: { series: "city", history: "all", presentation: "Canastilla", units: "25 Kilogramo" },
    options: { series: ["city"], presentations: ["Canastilla"], units: ["25 Kilogramo"], markets: [] },
  } }));
  await page.goto("/product/fixture-slash-city?series=city&history=all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const choice = page.getByRole("group", { name: "Consultar una fecha de esta tabla", exact: true });
  const search = choice.getByRole("combobox");
  const option = choice.getByRole("option", { name: /16 de agosto de 2021/ });
  for (const query of ["16/08/2021", "16/8/2021", "2021-08-16", "16 de agosto de 2021"]) {
    await search.fill(query);
    await expect(choice.getByRole("option")).toHaveCount(1);
    await expect(option).toBeVisible();
  }
  await option.click();
  const link = choice.getByRole("link", { name: "Consultar fuente de la fecha seleccionada", exact: true });
  const own = new URL((await link.getAttribute("href"))!, "http://fixture.invalid");
  expect(own.pathname).toBe(`/evidence/${documentId(16)}`);
  expect(Object.fromEntries(own.searchParams)).toMatchObject({ page: "16", month: day(16), market: "sipsa-bogota-corabastos" });
  await expect(page.locator(".chart-data tbody tr").filter({ hasText: "16 de agosto de 2021" })).toHaveCount(1);
  await search.fill("16/08/2022");
  await expect(choice.getByRole("option")).toHaveCount(0);
  await expect(link).toHaveAttribute("href", own.pathname + own.search);
  await search.fill("15/08/2021");
  await expect(choice.getByRole("option")).toHaveCount(1);
  await expect(choice.getByRole("option", { name: /15 de agosto de 2021/ })).toBeVisible();
  await expect(option).toHaveCount(0);
});

test("official history slash search keeps record identity, source page and date", async ({ page }) => {
  const history = Array.from({ length: 26 }, (_, index) => {
    const n = index + 1;
    return { id: "fixture-slash-reference", product_name: "Leche cruda", category: "Leche",
      publisher: "DANE", details: {}, market: "Costa Caribe", department: "", basis: "Precio mensual",
      price: 1000 + n, currency: "COP", unit: "litro", observed_on: day(n),
      document_id: documentId(n), source_page: n, source_locator: `PDF page ${n},row 1` };
  });
  await page.route("**/api/references?id=fixture-slash-reference", (route) => route.fulfill({ json: {
    reference: history.at(-1), history,
  } }));
  await page.goto("/references/fixture-slash-reference");
  await page.getByRole("combobox", { name: "Historial de precios", exact: true }).selectOption("all");
  await page.getByText("Ver datos en tabla", { exact: true }).click();
  const choice = page.getByRole("group", { name: "Consultar un registro de esta tabla", exact: true });
  const search = choice.getByRole("combobox");
  const option = choice.getByRole("option", { name: /16 de agosto de 2021/ });
  for (const query of ["16/08/2021", "16/8/2021", "2021-08-16", "16 de agosto de 2021"]) {
    await search.fill(query);
    await expect(choice.getByRole("option")).toHaveCount(1);
    await expect(option).toBeVisible();
  }
  await option.click();
  const link = choice.getByRole("link", { name: "Consultar fuente del registro seleccionado", exact: true });
  const own = new URL((await link.getAttribute("href"))!, "http://fixture.invalid");
  expect(own.pathname).toBe(`/evidence/${documentId(16)}`);
  expect(Object.fromEntries(own.searchParams)).toMatchObject({ page: "16", month: day(16), marketName: "Costa Caribe" });
  await search.fill("16/08/2022");
  await expect(choice.getByRole("option")).toHaveCount(0);
  await expect(link).toHaveAttribute("href", own.pathname + own.search);
  await search.fill("15/08/2021");
  await expect(choice.getByRole("option")).toHaveCount(1);
  await expect(choice.getByRole("option", { name: /15 de agosto de 2021/ })).toBeVisible();
  await expect(option).toHaveCount(0);
});
