import { expect, test } from "@playwright/test";

for (const kind of ["summary", "electricity", "wholesale"] as const) {
  test(`DANE ${kind} records have bounded exact choices and preserve original values and context`, async ({ page }) => {
    const electricity = kind === "electricity", wholesale = kind === "wholesale";
    const date = electricity ? "2020-12-31" : wholesale ? "2015-08-31" : "2026-08-31";
    const original = electricity ? "d1009999ad97fd1397713c5ada088d5f1698d44d19c13db99580fc831522dec5"
      : wholesale ? "31066705beb427300f977eb1f85923a9e481846f790fe033de16c00246bee198"
      : "05d573b725771fc451ca6914167b9c136fa7ab1f9410621defe0fa06c025c138";
    const target = {
      name: electricity ? "Electrificadora del Huila S.A. E.S.P. (ELECTROHUILA)" : wholesale ? "Ahuyama" : "10-20-20",
      category: electricity ? "Energía eléctrica" : wholesale ? "Productos mayoristas" : "Fertilizantes",
      observed_on: date, document_id: original,
      source_locator: electricity ? "3.5!row 3777" : wholesale ? "Anexo 1!row 7,col 2" : "Cuadro_resumen!row 93",
      details: electricity ? { Año: 2020, Mes: "Diciembre", Estrato: 5, "Tarifa Mes": 737.7672, Contribuciones: 0.2 }
        : wholesale ? { Ciudad: "Barranquilla", Unidad: "kg", "Precio (COP)": 1197, "Variación (%)": 40 }
        : { Presentación: "50 kilogramos", Municipios: 26, Disminución: 20, Estable: 6, Mínimo: 152000, Máximo: 215000 },
    };
    const rows = [...Array.from({ length: 12 }, (_, i) => ({
      ...target, name: `Ejemplo ${String(i + 1).padStart(2, "0")}`, source_locator: `fixture!row ${i + 1}`,
    })), target];
    await page.route("**/api/data-references?**", route => route.fulfill({ json: {
      kind, date, rows, total: rows.length, dates: [date], categories: [target.category], page: 0,
    } }));
    await page.goto("/data-references");
    if (kind !== "summary") await page.getByRole("combobox", { name: "Datos", exact: true }).selectOption(kind);
    const cards = page.locator("main article");
    await expect(cards).toHaveCount(6);
    await expect(page.getByLabel("Filtros aplicados")).toContainText(electricity ? "2020" : wholesale ? "2015" : "2026");
    const choice = page.getByRole("group", { name: "Consultar un registro de esta página", exact: true });
    const search = choice.getByRole("combobox");
    await search.click();
    await expect(choice.getByRole("option")).toHaveCount(8);
    await search.fill(electricity ? "huila" : wholesale ? "Ahuyama" : "10-20-20");
    await expect(cards).toHaveCount(6);
    await choice.getByRole("option").click();
    await expect(cards).toHaveCount(7);
    const selected = cards.filter({ has: page.getByRole("heading", { name: target.name, exact: true }) });
    if (electricity) {
      await expect(selected).toContainText("737,7672");
      await expect(selected).toContainText(/Contribuciones\s*20 %/);
      await expect(selected).not.toContainText(/Contribuciones\s*0,2/);
    } else if (wholesale) {
      await expect(selected).toContainText("1.197");
      await expect(selected).toContainText("40 %");
    } else {
      await expect(selected).toContainText("152.000");
      await expect(selected).toContainText("215.000");
    }
    const href = new URL((await selected.getByRole("link", { name: "Consultar fuente original", exact: true }).getAttribute("href"))!, "http://localhost");
    expect(href.pathname).toBe(`/evidence/${original}`);
    expect(href.searchParams.get("locator")).toBe(target.source_locator);
    expect(href.searchParams.get("month")).toBe(date);
    if (electricity) {
      expect(href.searchParams.get("providerName")).toBe(target.name);
      expect(href.searchParams.get("stratum")).toBe("5");
    } else expect(href.searchParams.get("productName")).toBe(target.name);
    await search.fill("nothingmatches-zzzz");
    await expect(selected).toBeVisible();
    await search.press("Escape");
    await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
    await expect(cards).toHaveCount(6);
  });
}

test("DANE record pagination keeps all pages accessible and clears the prior page's exact record", async ({ page }) => {
  const rows = Array.from({ length: 126 }, (_, i) => ({
    name: `Proveedor ${String(Math.floor(i / 6) + 1).padStart(2, "0")}`,
    category: "Energía eléctrica", document_id: "fixture-tariffs", source_locator: `3.5!row ${i + 1}`,
    observed_on: "2026-06-30", details: { Estrato: i % 6 + 1, "Tarifa mes": i + 0.1234 },
  }));
  await page.route("**/api/data-references?**", route => {
    const p = Number(new URL(route.request().url()).searchParams.get("page"));
    return route.fulfill({ json: { kind: "electricity", date: "2026-06-30", rows: rows.slice(p * 60, (p + 1) * 60),
      total: 126, dates: ["2026-06-30"], categories: ["Energía eléctrica"], page: p } });
  });
  await page.goto("/data-references?kind=electricity");
  await expect(page.locator("main article")).toHaveCount(6);
  await expect(page.locator("main")).toContainText("Página 1 de 3 · registros 1–60 de 126");
  const choice = page.getByRole("group", { name: "Consultar un registro de esta página", exact: true });
  await choice.getByRole("combobox").fill("Proveedor 10 · Estrato 6");
  await choice.getByRole("option").click();
  await expect(page.locator("main article")).toHaveCount(7);
  await expect(page.locator("main article").last()).toContainText("59,1234");
  await page.getByRole("button", { name: "Siguiente →", exact: true }).click();
  await expect(page.locator("main")).toContainText("Página 2 de 3 · registros 61–120 de 126");
  await expect(page.locator("main article")).toHaveCount(6);
  await expect(choice).not.toContainText("Seleccionado:");
  await expect(page.locator("main article").first()).toContainText("Proveedor 11");
  await page.getByRole("button", { name: "Siguiente →", exact: true }).click();
  await expect(page.locator("main")).toContainText("Página 3 de 3 · registros 121–126 de 126");
  await expect(page.locator("main article")).toHaveCount(6);
  await expect(choice).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Siguiente →", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "← Anterior", exact: true }).click();
  await expect(page.locator("main")).toContainText("Página 2 de 3");
  await expect(page.locator("main article")).toHaveCount(6);
});
