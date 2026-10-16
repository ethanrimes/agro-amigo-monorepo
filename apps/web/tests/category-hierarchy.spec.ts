import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { categoryChoices, categoryMatches, productCategoryPaths } from "../src/lib/category-hierarchy";
import { paginateCatalog } from "../src/lib/catalog-page";
import type { UnifiedCatalog } from "../src/lib/catalog-types";

test("only observed source paths create parents; selecting one retains prices, IDs and sources", () => {
  const paths = ["Frutas > Cítricos", "Frutas > Tropicales", "Frutas frescas", "Tubérculos, raíces y plátanos > Plátano"];
  expect(categoryChoices(paths).map((choice) => choice.id)).toContain("Frutas");
  expect(categoryChoices(paths).map((choice) => choice.id)).not.toContain("Frutas > Frescas");
  expect(categoryMatches("Frutas > Cítricos", "Frutas")).toBe(true);
  expect(categoryMatches("Frutas > Cítricos", "frutas > citricos")).toBe(true);
  expect(categoryMatches("Frutas frescas", "Frutas")).toBe(false);
  expect(categoryMatches("Tubérculos, raíces y plátanos > Plátano", "Tubérculos")).toBe(false);
  expect(categoryMatches("Niños > Plátano", "Ninos")).toBe(true);
  expect(categoryMatches("Nin\u0303os > Plátano", "NINOS")).toBe(true);
  expect(categoryMatches("Frutas (frescas) > Cítricos", "Frutas frescas")).toBe(false);
  const products = paths.map((category, index) => ({
    id: `id-${index}`, identity: `quote-${index}`, name: `Producto ${index}`,
    category, price: index + 100, document_id: `${index}`.padStart(64, "0"), source_locator: `row ${index}`,
  }));
  const catalog = { products, regions: [], latestDate: null, filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null } } as unknown as UnifiedCatalog;
  const parent = paginateCatalog(catalog, { category: "Frutas", limit: 24 });
  expect(parent.products).toEqual(products.slice(0, 2));
  expect(parent.total).toBe(2);
  expect(paginateCatalog(catalog, { category: "Frutas > Cítricos" }).products).toEqual([products[0]]);
  expect(paginateCatalog(catalog, { category: "Frutas frescas" }).products).toEqual([products[2]]);
  const explicit = { ...products[0], category: "Frutas", category_paths: [["Frutas", "Cítricos"], ["Frutas", "Tropicales"]] };
  expect(productCategoryPaths(explicit)).toEqual(["Frutas > Cítricos", "Frutas > Tropicales"]);
  const classified = { ...catalog, products: [explicit] } as unknown as UnifiedCatalog;
  expect(paginateCatalog(classified, { category: "frutas > citricos" }).products).toEqual([explicit]);
  expect(paginateCatalog(classified, { category: "Frutas frescas" }).products).toEqual([]);
  expect(paginateCatalog(classified, {}).categories).toEqual(["Frutas > Cítricos", "Frutas > Tropicales"]);
});

test("accent-equivalent category filters retain distinct source choice IDs", () => {
  const paths = ["Cultivos > Cana", "Cultivos > Caña", "Cultivos > Cítricos"];
  expect(categoryChoices(paths).filter((choice) => choice.depth === 2).map((choice) => choice.id))
    .toEqual(["Cultivos > Cana", "Cultivos > Caña", "Cultivos > Cítricos"]);
  expect(categoryMatches("Cultivos > Caña", "cultivos > CANA")).toBe(true);
  expect(categoryMatches("Cultivos > Cana", "Cultivos > Can\u0303a")).toBe(true);
  expect(categoryMatches("Cultivos > Cítricos", "Cultivos > Ci\u0301tricos")).toBe(true);
  expect(categoryMatches("Cultivos > Caña", "Cultivos")).toBe(true);
  expect(categoryMatches("Cultivos > Caña", "Cultivos > Cana > Extra")).toBe(false);
});

test("Bogotá monthly Limón Tahití retains its current native city citrus path without changing its quote", async ({ request }) => {
  const query = async (category: string) => {
    const response = await request.post("/api/catalog", { data: {
      region: "Bogotá, D.C.", q: "LIMON TAHITI", category, limit: 100,
    } });
    expect(response.ok()).toBeTruthy();
    return (await response.json()).products as Array<{
      id: string; kind: string; category: string; category_paths?: string[][];
      price: number; date: string; series: string; href: string;
    }>;
  };
  const canonical = (await query("Todos")).find((product) => product.id === "limon-tahiti");
  expect(canonical).toMatchObject({ id: "limon-tahiti", kind: "product", series: "monthly" });
  const child = (await query("Frutas > CI\u0301TRICOS")).find((product) => product.id === "limon-tahiti");
  expect(child).toMatchObject({
    id: canonical!.id, kind: canonical!.kind, price: canonical!.price,
    date: canonical!.date, series: canonical!.series, href: canonical!.href,
    category_paths: expect.arrayContaining([["Frutas", "Cítricos"]]),
  });
  expect((await query("Frutas")).some((product) => product.id === "limon-tahiti")).toBe(true);
  expect((await query("Frutas > Otras frutas")).some((product) => product.id === "limon-tahiti")).toBe(false);
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 720 }]) {
  test(`category hierarchy supports query, keyboard choice, breadcrumb and clear at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.route("**/api/catalog", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const category = route.request().postDataJSON()?.category || "Todos";
      const total = category === "Frutas" ? 2 : category === "Frutas > Cítricos" ? 1 : 4;
      await route.fulfill({ json: {
        products: [], regions: [], latestDate: null,
        filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
        categories: ["Frutas > Cítricos", "Frutas > Tropicales", "Frutas frescas", "Tubérculos, raíces y plátanos > Plátano"],
        currencies: ["COP"], total, pagination: { offset: 0, limit: 24, has_more: false }, map_product: null,
      } });
    });
    await page.goto("/products");
    const control = page.getByRole("group", { name: "Categoría", exact: true });
    const search = control.getByRole("combobox");
    const child = control.getByRole("option", { name: /Frutas > Cítricos/ });
    for (const query of ["CITRICOS", "CÍTRICOS", "ci\u0301tricos", "citricos"]) {
      await search.fill(query);
      await expect(control).toHaveAttribute("data-selected-value", "");
      await expect(child).toBeVisible();
    }
    await expect(child.locator(".hierarchy-branch")).toBeVisible();
    await expect(child.locator("strong")).toHaveText("Cítricos");
    await search.press("ArrowDown");
    await search.press("Enter");
    await expect(control).toHaveAttribute("data-selected-value", "Frutas > Cítricos");
    await expect(control).toContainText("Seleccionado: Frutas > Cítricos");
    await expect(page).toHaveURL(/category=Frutas\+%3E\+C%C3%ADtricos/);
    await search.fill("no-existe");
    await expect(control).toHaveAttribute("data-selected-value", "Frutas > Cítricos");
    await search.press("Escape");
    await control.getByRole("button", { name: "Quitar selección" }).click();
    await expect(control).toHaveAttribute("data-selected-value", "");
    await search.fill("frutas");
    if (viewport.width === 390 && testInfo.project.name === "mobile") {
      const path = resolve(__dirname, "../../../artifacts/qa-resumed-20261001/category-hierarchy-web-g-mobile-options-20261004.png");
      mkdirSync(dirname(path), { recursive: true });
      await page.screenshot({ path });
    }
    await control.getByRole("option", { name: /^Frutas · Incluye/ }).click();
    await expect(control).toHaveAttribute("data-selected-value", "Frutas");
    await expect(page.getByText("Categoría: Frutas")).toBeVisible();
  });
}

test("city reports use the same parent hierarchy without changing the exact source link", async ({ page }) => {
  const row = (product_name: string, product_id: string, category_path: string[], document_id: string) => ({
    product_name, product_id, category_path, document_id,
    market_id: "market-1", market_name: "Barranquilla, Barranquillita", source_page: 1,
    source_locator: "PDF page 1,table 1,row 21,round 1", observed_on: "2026-10-02",
    presentation: "Caja de cartón", quantity: 2.5, source_unit: "Kilogramo", round: 1,
    round_label: "Ronda 1", min_price: 20_000, max_price: 21_000,
    unit: "kg", min_unit_price: 8_000, max_unit_price: 8_400,
  });
  const did = "5ec147f7068d6b7ac01f441cfe050ecfb839a3108fc514299ebe36ddc8869ada";
  await page.route("**/api/planning/regional", (route) => route.fulfill({ json: [
    row("Mora de Castilla", "mora", ["Frutas", "Bayas"], did),
    row("Limón Tahití", "limon", ["Frutas frescas"], "a".repeat(64)),
  ] }));
  await page.goto("/regional");
  const control = page.getByRole("group", { name: "Categoría", exact: true });
  await control.getByRole("combobox").fill("frutas");
  await control.getByRole("option", { name: /^Frutas · Incluye/ }).click();
  await expect(page.getByRole("heading", { name: "Mora de Castilla" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Limón Tahití" })).toHaveCount(0);
  const source = page.getByRole("link", { name: /Consultar fuente/ });
  await expect(source).toHaveAttribute("href", new RegExp(did));
  await expect(source).toHaveAttribute("href", /page=1/);
});

test("category search reports pending metadata before showing source-supported children", async ({ page }) => {
  let releaseMetadata!: () => void;
  const pendingMetadata = new Promise<void>((resolve) => { releaseMetadata = resolve; });
  await page.route("**/api/catalog", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await pendingMetadata;
    await route.fulfill({ json: {
      products: [], regions: [], latestDate: null,
      filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
      categories: ["Frutas > Cítricos", "Frutas frescas"], currencies: ["COP"],
      total: 0, pagination: { offset: 0, limit: 24, has_more: false }, map_product: null,
    } });
  });
  await page.goto("/products");
  const control = page.getByRole("group", { name: "Categoría", exact: true });
  const search = control.getByRole("combobox");
  await search.fill("citricos");
  await expect(control).toContainText("Buscando sugerencias…");
  await expect(control).not.toContainText("Sin coincidencias");
  await expect(control).toHaveAttribute("data-selected-value", "");
  releaseMetadata();
  await expect(control.getByRole("option", { name: /Frutas > Cítricos/ })).toBeVisible();
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(control).toHaveAttribute("data-selected-value", "Frutas > Cítricos");
  await expect(control).toContainText("Seleccionado: Frutas > Cítricos");
});
