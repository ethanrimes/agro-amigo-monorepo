import { expect, test } from "@playwright/test";

test("supply map retains regional month scope and every contributing original with searchable source choices", async ({ page }) => {
  const id = "fixture-supply-papa", a = "a".repeat(64), b = "b".repeat(64);
  const product = { id, name: "Papa única", category: "Tubérculos", image_key: "produce",
    price: 2000, date: "2022-07-31", unit: "kg", market_count: 1, source: "DANE", period: "monthly" };
  await page.route("**/api/catalog?**", route => route.fulfill({ json: {
    products: [product], regions: ["Atlántico"], latestDate: product.date,
  } }));
  await page.route(`**/api/products/${id}?**`, route => route.fulfill({ json: {
    product, classification: [["Tubérculos"]], additional_references: [], markets: [],
    current: { date: product.date, price: 2000, market_count: 1 }, history: [],
    filters: { region: "Atlántico", series: "monthly", presentation: "Por unidad de medida", units: "1 kg", history: "all" },
    options: { series: ["monthly"], markets: [], presentations: ["Por unidad de medida"], units: ["1 kg"] },
  } }));
  await page.route("**/api/explore/map?**", route => {
    const query = new URL(route.request().url()).searchParams;
    expect(query.get("region")).toBe("Atlántico");
    expect(query.get("history")).toBe("all");
    const supply = query.get("mode") === "supply";
    return route.fulfill({ json: { points: [{ id: "barranquillita", name: "Barranquilla, Barranquillita",
      region: "Atlántico", department_id: "08", latitude: 10.96, longitude: -74.78,
      value: supply ? 31 : 2000, date: "2022-07-29", unit: supply ? "kg" : "COP / kg",
      ...(supply ? { period_start: "2022-07-01", sources: [
        { document_id: a, title: "Anexo Cítricos.xlsx" }, { document_id: b, title: "Anexo Bogotá.xlsx" },
      ] } : { document_id: a }),
    }], unit: supply ? "kg" : "COP / kg", date: "2022-07-29", period_start: supply ? "2022-07-01" : undefined,
      filters: supply ? { region: "Atlántico", history: "all" } : { region: "Atlántico", history: "all",
        series: "monthly", presentation: "Por unidad de medida", units: "1 kg" },
      basis: supply ? "Llegadas reportadas en el último mes disponible." : "Precio de prueba",
    } });
  });
  await page.goto(`/product/${id}?region=Atl%C3%A1ntico&history=all`);
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Productos en Colombia", exact: true });
  await map.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Departamento: Atlántico");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Mes reportado: julio de 2022");
  await expect(map.getByLabel("Filtros aplicados")).not.toContainText("Por unidad de medida");
  await expect(map.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
  await map.getByRole("combobox", { name: "Abrir abastecimiento de un departamento", exact: true }).fill("ATLANTICO");
  await expect(map.getByRole("option", { name: "Antioquia", exact: true })).toHaveCount(0);
  await map.getByRole("option", { name: "Atlántico", exact: true }).click();
  const quote = map.locator(".map-popup-quotes article");
  await expect(quote).toContainText("31");
  await expect(quote).toContainText("kg");
  const source = quote.getByRole("combobox", { name: "Archivo de abastecimiento", exact: true });
  for (const query of ["ANEXO BOGOTA", "anexo Bogotá", "anexo Bogota\u0301"]) {
    await source.fill(query);
    await expect(quote.getByRole("option", { name: "Anexo Bogotá.xlsx", exact: true })).toBeVisible();
  }
  await quote.getByRole("option", { name: "Anexo Bogotá.xlsx", exact: true }).click();
  let url = new URL(await quote.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href") || "", "http://localhost");
  expect(url.pathname).toBe("/evidence/" + b);
  expect(url.searchParams.get("month")).toBe("2022-07-01");
  expect(url.searchParams.get("product")).toBe(id);
  expect(url.searchParams.get("market")).toBe("barranquillita");
  expect(url.searchParams.get("department")).toBe("Atlántico");
  expect(url.searchParams.get("units")).toBe("kg");
  expect(url.searchParams.has("presentation")).toBe(false);
  await source.fill("CITRICOS");
  await quote.getByRole("option", { name: "Anexo Cítricos.xlsx", exact: true }).click();
  url = new URL(await quote.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href") || "", "http://localhost");
  expect(url.pathname).toBe("/evidence/" + a);
  expect(url.searchParams.get("month")).toBe("2022-07-01");
});

test("catalog map retains the selected source hierarchy and keeps it when choosing another product", async ({ page }) => {
  const date = "2025-06-25", original = "9".repeat(64);
  const citrus = (id: string, name: string) => ({ id, identity: id, name, category: "Frutas",
    category_paths: [["Frutas", "Cítricos"]], image_key: "produce", price: 269_000,
    previous_price: null, date, unit: "kg", market_count: 1, source: "DANE", period: "daily",
    series: "city", presentation: "Bulto", units: "50 Kilogramo", kind: "product", currency: "COP", map_supported: true });
  const products = [citrus("fixture-map-limon", "Limón común Ciénaga"), citrus("fixture-map-naranja", "Naranja Valencia"),
    { ...citrus("fixture-map-flat", "Fruta independiente"), category: "Frutas frescas", category_paths: undefined }];
  await page.route("**/api/catalog", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({ json: { products: products.slice(0, 2), regions: ["Atlántico"], latestDate: date,
      filters: { region: "Atlántico", reference_scope: "regional-only", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
      categories: ["Frutas > Cítricos", "Frutas frescas"], currencies: ["COP"], total: 2,
      pagination: { offset: 0, limit: 24, has_more: false }, map_product: products[0] } });
  });
  await page.route("**/api/catalog?**", (route) => {
    const query = new URL(route.request().url()).searchParams;
    // The global latest quote classifies this ID differently. The regional
    // catalog must be requested to retain its source's citrus classification.
    const choices = query.get("region") === "Atlántico" ? products : products.map(p => p.id === "fixture-map-naranja"
      ? { ...p, category_paths: [["Frutas", "Otras frutas"]] } : p);
    return route.fulfill({ json: { products: choices, regions: ["Atlántico"], latestDate: date } });
  });
  await page.route("**/api/explore/map?**", (route) => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: {
      points: [{ id: "fixture-barranquillita", name: "Barranquilla, Barranquillita", region: "Atlántico", department_id: "08",
        latitude: 10.96, longitude: -74.78, value: 269_000, date, unit: "COP / Bulto · 50 Kilogramo", series: "city",
        min_price: 268_000, max_price: 270_000, document_id: original, source_page: 1,
        source_locator: "PDF page 1,table 1,row 12,round 1", presentation: "Bulto", units: "50 Kilogramo" }],
      unit: "COP / Bulto · 50 Kilogramo", date, basis: "Source-shaped city quote; computed midpoint",
      selection_label: products.find(p => p.id === query.get("id"))?.name,
      filters: { region: query.get("region") || "", series: "city", presentation: "Bulto", units: "50 Kilogramo", history: query.get("history") || "recent" },
      options: { series: ["city"], markets: [], presentations: ["Bulto"], units: ["50 Kilogramo"] },
    } });
  });
  await page.goto("/products?region=Atl%C3%A1ntico&category=Frutas+%3E+C%C3%ADtricos");
  const firstRequest = page.waitForRequest((request) => request.url().includes("/api/explore/map?"));
  const catalogRequest = page.waitForRequest((request) => request.url().includes("/api/catalog?") && new URL(request.url()).searchParams.get("view") === "canonical");
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  const first = new URL((await firstRequest).url()).searchParams;
  expect(first.get("category")).toBe("Frutas > Cítricos");
  expect(first.get("region")).toBe("Atlántico");
  expect(first.get("history")).toBe("all");
  expect(new URL((await catalogRequest).url()).searchParams.get("region")).toBe("Atlántico");
  const map = page.getByRole("dialog", { name: "Productos en Colombia", exact: true });
  const category = map.getByRole("group", { name: "Categoría en mapa", exact: true });
  await expect(category).toHaveAttribute("data-selected-value", "Frutas > Cítricos");
  await category.getByRole("combobox").fill("citricos");
  await expect(category.getByRole("option", { name: /Frutas > Cítricos/ })).toBeVisible();
  await category.getByRole("combobox").press("Escape");
  const product = map.getByRole("combobox", { name: "Elegir producto en el mapa", exact: true });
  await product.fill("Fruta independiente");
  await expect(map.getByRole("option", { name: "Fruta independiente", exact: true })).toHaveCount(0);
  await product.fill("naranja");
  const nextRequest = page.waitForRequest((request) => request.url().includes("/api/explore/map?") && new URL(request.url()).searchParams.get("id") === "fixture-map-naranja");
  await map.getByRole("option", { name: "Naranja Valencia", exact: true }).click();
  const next = new URL((await nextRequest).url()).searchParams;
  expect(next.get("category")).toBe("Frutas > Cítricos");
  expect(next.get("region")).toBe("Atlántico");
  expect(next.get("history")).toBe("all");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Categoría: Frutas > Cítricos");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Departamento: Atlántico");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Historial: Todo el historial");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Producto: Naranja Valencia");
  await expect(map.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
  await map.getByRole("combobox", { name: "Abrir precios de un departamento", exact: true }).fill("atlantico");
  await map.getByRole("option", { name: "Atlántico", exact: true }).click();
  const quote = map.locator(".map-popup-quotes article");
  await expect(quote).toContainText(/269.000/);
  await expect(quote).toContainText("50 Kilogramo");
  await expect(quote.getByRole("link", { name: "Consultar fuente", exact: true })).toHaveAttribute("href", new RegExp(original));
  await product.fill("LIMON");
  await expect(map.getByRole("option", { name: "Limón común Ciénaga", exact: true })).toBeVisible();
  await product.fill("limón");
  await map.getByRole("option", { name: "Limón común Ciénaga", exact: true }).click();
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Producto: Limón común Ciénaga");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Categoría: Frutas > Cítricos");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Departamento: Atlántico");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Historial: Todo el historial");
  for (const categoryValue of ["Frutas", "Frutas > Cítricos", ""]) {
    const changed = page.waitForRequest((request) => {
      if (!request.url().includes("/api/explore/map?")) return false;
      const query = new URL(request.url()).searchParams;
      return query.get("category") === categoryValue;
    });
    if (categoryValue) {
      await category.getByRole("combobox").fill(categoryValue === "Frutas" ? "FRUTAS" : "CITRICOS");
      await category.getByRole("option", {
        name: categoryValue === "Frutas" ? /^Frutas · Incluye/ : /Frutas > Cítricos/,
      }).click();
    } else {
      await category.getByRole("button", { name: "Quitar selección", exact: true }).click();
    }
    const preserved = new URL((await changed).url()).searchParams;
    expect(preserved.get("id")).toBe("fixture-map-limon");
    expect(preserved.get("region")).toBe("Atlántico");
    expect(preserved.get("history")).toBe("all");
    await expect(map.getByLabel("Filtros aplicados")).toContainText("Producto: Limón común Ciénaga");
    await expect(map.getByLabel("Filtros aplicados")).toContainText("50 Kilogramo");
  }
  await category.getByRole("combobox").fill("Frutas frescas");
  await category.getByRole("option", { name: /^Frutas frescas ·/ }).click();
  await expect(product).not.toHaveValue("Limón común Ciénaga");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Categoría: Frutas frescas");
});

for (const series of ["city", "mill"] as const) {
  test(`map ${series} preserves exact date/source/unit and distinguishes computed city midpoint`, async ({ page }) => {
    const city = series === "city";
    const id = `fixture-map-${series}`;
    const original = city ? "cef8b53d3954fd4c6be1b3978b7d296e7f6f9c05ffa3544af3d111b718a7ac7d" : "55671429ad35195607275009f25ad6cfa91b773be0337ec4ee4af748daa90d52";
    const name = city ? "Ahuyama" : "Arroz paddy verde · en molino";
    const placeName = city ? "Duitama (Boyacá), Mercaplaza" : "ALVARADO · molinos";
    const region = city ? "Boyacá" : "Tolima";
    const units = city ? "32 Kilogramo" : "1 kg";
    const presentation = city ? "Bulto" : "Por unidad de medida";
    const date = city ? "2026-10-02" : "2025-11-30";
    const price = city ? 46_500 : 1_480;
    const target = { id: city ? "sipsa-duitama-boyaca-mercaplaza" : "molino-tolima-alvarado", name: placeName, region, department_id: city ? "15" : "73", latitude: city ? 5.82 : 4.57, longitude: city ? -73.03 : -74.95,
      value: price, date, unit: `COP / ${presentation} · ${units}`, series,
      min_price: city ? 45_000 : null, max_price: city ? 48_000 : null,
      document_id: original, source_page: city ? 2 : 1, source_locator: city ? "PDF page 2,table 1,row 7,round 1" : "Hoja1!row 1039; COP/tonelada dividido entre 1000 = COP/kg", presentation, units };
    const points = city ? [...Array.from({ length: 12 }, (_, i) => ({ ...target, id: `market-${i}`, name: `Mercado ${String(i + 1).padStart(2, "0")}`, value: 60_000 + i, min_price: 59_000 + i, max_price: 61_000 + i })), target] : [target];
    await page.route("**/api/catalog?**", route => route.fulfill({ json: { products: [{ id, name, category: "Hortalizas", image_key: "produce", price, date, unit: "kg", market_count: points.length, source: "dane", period: "daily", series, presentation, units }], regions: [region], latestDate: date } }));
    await page.route(`**/api/products/${id}?**`, route => route.fulfill({ json: {
      product: { id, name, category: "Hortalizas", image_key: "produce" },
      classification: [["Hortalizas"]], additional_references: [], markets: [],
      current: { date, price, market_count: 1 }, history: [{ date, price, sources: [] }],
      filters: { region: "", series, market: "", presentation, units, history: "all" },
      options: { series: [series], markets: [], presentations: [presentation], units: [units] },
    } }));
    await page.route("**/api/explore/map?**", route => route.fulfill({ json: {
      points, unit: target.unit, date, basis: "Fixture of exact source ranges and dates",
      filters: { series, presentation, units, history: "all" },
      options: { series: [series], markets: [], presentations: [presentation], units: [units] },
    } }));
    await page.goto(`/product/${id}?series=${series}&presentation=${encodeURIComponent(presentation)}&units=${encodeURIComponent(units)}&history=all`);
    await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
    const map = page.getByRole("dialog", { name: "Productos en Colombia", exact: true });
    await expect(map.getByLabel("Filtros aplicados")).toContainText("Historial: Todo el historial");
    await expect(map.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
    await map.getByRole("combobox", { name: "Abrir precios de un departamento", exact: true }).fill(city ? "boyaca" : "tolima");
    await map.getByRole("option", { name: region, exact: true }).click();
    const popup = map.locator(".map-popup-quotes");
    await expect(popup.getByRole("article")).toHaveCount(city ? 6 : 1);
    if (city) {
      const choice = map.getByRole("group", { name: "Consultar precio en este lugar", exact: true });
      await choice.getByRole("combobox").click();
      await expect(choice.getByRole("option")).toHaveCount(8);
      await choice.getByRole("combobox").fill("duitama");
      await expect(popup.getByRole("article")).toHaveCount(6);
      await choice.getByRole("option", { name: /Duitama.*46.500.*32 Kilogramo/ }).click();
      await expect(popup.getByRole("article")).toHaveCount(7);
    }
    const row = popup.getByRole("article").filter({ hasText: placeName });
    if (city) await expect(row.getByRole("link", { name: "Consultar fuente", exact: true })).toBeInViewport();
    await expect(row).toContainText(city ? /46.500/ : /1.480/);
    await expect(row).toContainText(units);
    await expect(row).toContainText(city ? "2 de octubre de 2026" : "30 de noviembre de 2025");
    if (city) {
      await expect(row).toContainText("Punto medio calculado del rango");
      await expect(row).toContainText(/Rango publicado:.*45.000.*48.000/);
    } else {
      await expect(row).not.toContainText("Punto medio");
      await expect(row).not.toContainText("Rango publicado");
    }
    const href = new URL((await row.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href"))!, "http://localhost");
    expect(href.pathname).toBe(`/evidence/${original}`);
    expect(href.searchParams.get("page")).toBe(city ? "2" : "1");
    expect(href.searchParams.get("locator")).toBe(target.source_locator);
    expect(href.searchParams.get("month")).toBe(date);
    expect(href.searchParams.get("units")).toBe(units);
    expect(href.searchParams.get("presentation")).toBe(presentation);
    if (city) {
      const choice = map.getByRole("group", { name: "Consultar precio en este lugar", exact: true });
      await choice.getByRole("combobox").fill("no-match-zzzz");
      await expect(row).toContainText("Duitama (Boyacá), Mercaplaza");
      await choice.getByRole("combobox").press("Escape");
      await expect(map).toBeVisible();
      await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
      await expect(popup.getByRole("article")).toHaveCount(6);
    }
  });
}

test("late input options preserve the user's search and apply only the exact chosen identity", async ({ page }) => {
  const rows = [
    { id: "fixture-default", name: "0-5-0", presentation: "50 kilogramos", category: "Fertilizantes" },
    { id: "fixture-ethrel", name: "Ethrel 48 Sl", presentation: "200 centímetros cúbicos", category: "Reguladores" },
  ].map(input => ({ ...input, department: "Valle del Cauca", municipality: "Dagua", price: 71_450, observed_on: "2024-01-31", brand: null, registration: null, product_line: null }));
  let releaseOptions!: () => void;
  const optionsReady = new Promise<void>(resolve => { releaseOptions = resolve; });
  await page.route("**/api/planning/inputs?**", async route => {
    if (new URL(route.request().url()).searchParams.get("history") === "all") await optionsReady;
    await route.fulfill({ json: rows });
  });
  const original = "73cc2a774fdac47799294fb9849c8c4c62a20d291b29782bd1b46c12fdc525ec";
  await page.route("**/api/explore/map?**", route => route.fulfill({ json: {
    points: new URL(route.request().url()).searchParams.get("id") === "fixture-ethrel" ? [{
      id: "76233", name: "Dagua, Valle del Cauca", municipality: "Dagua", region: "Valle del Cauca", department_id: "76",
      latitude: 3.65, longitude: -76.69, value: 71_450, date: "2024-01-31", unit: "COP / 200 centímetros cúbicos",
      document_id: original, source_locator: "1.1!row 254; column 9", presentation: "200 centímetros cúbicos",
    }] : [], unit: "COP / 200 centímetros cúbicos", date: "2024-01-31", basis: "Fixture of delayed official input choices", filters: { scope: "municipality" },
  } }));
  await page.goto("/insumos?scope=municipality&department=&history=all");
  const optionRequest = page.waitForRequest(request => request.url().includes("/api/planning/inputs?") && new URL(request.url()).searchParams.get("grouped") === "true");
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Insumos en Colombia", exact: true });
  const search = map.getByRole("combobox", { name: "Elegir insumo en el mapa", exact: true });
  await search.fill("ethrel");
  expect(new URL((await optionRequest).url()).searchParams.get("history")).toBe("all");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Historial: Todo el historial");
  await expect(map.getByRole("option")).toHaveCount(0);
  releaseOptions();
  await expect(map.getByRole("option", { name: "Ethrel 48 Sl · 200 centímetros cúbicos", exact: true })).toBeVisible();
  await expect(search).toHaveValue("ethrel");
  await expect(map.getByLabel("Filtros aplicados")).toContainText(/Producto:\s*Todos/);
  await map.getByRole("option", { name: "Ethrel 48 Sl · 200 centímetros cúbicos", exact: true }).click();
  await expect(search).toHaveValue("Ethrel 48 Sl · 200 centímetros cúbicos");
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Ethrel 48 Sl · 200 centímetros cúbicos");
  await expect(map.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
  await map.getByRole("combobox", { name: "Abrir precios de un departamento", exact: true }).fill("valle");
  await map.getByRole("option", { name: "Valle del Cauca", exact: true }).click();
  const row = map.locator(".map-popup-quotes article");
  await expect(row).toContainText("31 de enero de 2024");
  const href = new URL((await row.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${original}`);
  expect(href.searchParams.get("municipality")).toBe("Dagua");
  expect(href.searchParams.get("department")).toBe("Valle del Cauca");
  expect(href.searchParams.get("month")).toBe("2024-01-31");
  expect(href.searchParams.get("input")).toBe("fixture-ethrel");
});

test("input map choices follow the requested history period without including old-only IDs in recent data", async ({ page }) => {
  const oldInput = { id: "fixture-agrotin-2014", name: "Agrotin SL", presentation: "1 litro 1234",
    category: "Coadyuvantes", department: "Quindío", municipality: "Armenia", price: 13_883,
    observed_on: "2014-03-31" };
  await page.route("**/api/planning/inputs?**", route => route.fulfill({ json:
    new URL(route.request().url()).searchParams.get("history") === "all" ? [oldInput] : [] }));
  await page.route("**/api/explore/map?**", route => {
    const query = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: { points: [], unit: "referencias", date: null, basis: "History scope fixture",
      filters: { scope: "municipality", region: query.get("region") || "", history: query.get("history") || "recent" } } });
  });
  for (const history of ["recent", "all", "recent"]) {
    await page.goto(`/insumos?scope=municipality&department=Quind%C3%ADo&history=${history}`);
    const request = page.waitForRequest(request => {
      if (!request.url().includes("/api/planning/inputs?")) return false;
      const query = new URL(request.url()).searchParams;
      // The underlying page can still request its default options during
      // hydration. Observe the map lookup, which explicitly sends its period.
      return query.get("grouped") === "true" && query.has("history");
    });
    await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
    const query = new URL((await request).url()).searchParams;
    expect(query.get("history")).toBe(history);
    expect(query.get("department")).toBe("Quindío");
    expect(query.get("scope")).toBe("municipality");
    const map = page.getByRole("dialog", { name: "Insumos en Colombia", exact: true });
    await expect(map.getByLabel("Filtros aplicados")).toContainText(history === "all" ? "Historial: Todo el historial" : "Historial: Últimos 12 meses");
    const search = map.getByRole("combobox", { name: "Elegir insumo en el mapa", exact: true });
    if (history === "all") {
      await expect(search).toHaveValue("Agrotin SL · 1 litro 1234");
      await map.getByRole("button", { name: "Borrar elegir insumo en el mapa", exact: true }).click();
      await expect(search).toHaveValue("");
    }
    await search.fill("AGROTIN");
    const choice = map.getByRole("option", { name: "Agrotin SL · 1 litro 1234", exact: true });
    if (history === "all") await expect(choice).toBeVisible();
    else await expect(choice).toHaveCount(0);
    await map.getByRole("button", { name: "Cerrar ventana", exact: true }).click();
  }
});

test("a focused input-map search survives the first delayed all-history option response", async ({ page }) => {
  const oldInput = { id: "fixture-agrotin-2014", name: "Agrotin SL", presentation: "1 litro 1234",
    category: "Coadyuvantes", department: "Quindío", municipality: "Armenia", price: 13_883,
    observed_on: "2014-03-31" };
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/planning/inputs?**", async route => {
    const history = new URL(route.request().url()).searchParams.get("history");
    if (history === "all") await pending;
    await route.fulfill({ json: history === "all" ? [oldInput] : [] });
  });
  await page.route("**/api/explore/map?**", route => route.fulfill({ json: {
    points: [], unit: "referencias", date: null, basis: "Delayed source fixture",
    filters: { scope: "municipality", history: "all" },
  } }));
  await page.goto("/insumos?scope=municipality&department=Quind%C3%ADo&history=all");
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Insumos en Colombia", exact: true });
  const search = map.getByRole("combobox", { name: "Elegir insumo en el mapa", exact: true });
  await search.focus();
  await search.fill("AGROTIN");
  release();
  await expect(search).toHaveValue("AGROTIN");
  await expect(map.getByRole("option", { name: "Agrotin SL · 1 litro 1234", exact: true })).toBeVisible();
  await map.getByRole("option", { name: "Agrotin SL · 1 litro 1234", exact: true }).click();
  await expect(map.getByLabel("Filtros aplicados")).toContainText("Agrotin SL · 1 litro 1234");
});

test("a compact phone map scrolls the chosen old-year input and its source into view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  const original = "73cc2a774fdac47799294fb9849c8c4c62a20d291b29782bd1b46c12fdc525ec";
  const target = { id: "76233", name: "Dagua, Valle del Cauca", municipality: "Dagua", region: "Valle del Cauca", department_id: "76",
    latitude: 3.65, longitude: -76.69, value: 71_450, date: "2024-01-31", unit: "COP / 200 centímetros cúbicos",
    document_id: original, source_locator: "1.1!row 254; column 9", presentation: "200 centímetros cúbicos" };
  await page.route("**/api/planning/inputs?**", route => route.fulfill({ json: [{ id: "fixture-ethrel", name: "Ethrel 48 Sl", presentation: "200 centímetros cúbicos", category: "Reguladores", department: "Valle del Cauca", municipality: "Dagua", price: 71_450, observed_on: "2024-01-31" }] }));
  await page.route("**/api/explore/map?**", route => route.fulfill({ json: {
    points: [...Array.from({ length: 6 }, (_, i) => ({ ...target, id: `fixture-${i}`, name: `Municipio ${i}, Valle del Cauca`, value: 80_000 + i, date: "2026-08-31" })), target],
    unit: target.unit, date: "2026-08-31", basis: "Fixture of seven source-bound municipal prices", filters: { scope: "municipality" },
  } }));
  await page.goto("/insumos?scope=municipality&department=&history=all");
  await page.getByRole("button", { name: "Ver mapa", exact: true }).click();
  const map = page.getByRole("dialog", { name: "Insumos en Colombia", exact: true });
  await expect(map.locator(".colombia-map")).toHaveAttribute("data-ready", "true");
  await map.getByRole("combobox", { name: "Abrir precios de un departamento", exact: true }).fill("valle");
  await map.getByRole("option", { name: "Valle del Cauca", exact: true }).click();
  const choice = map.getByRole("group", { name: "Consultar precio en este lugar", exact: true });
  await choice.getByRole("combobox").fill("dagua");
  await choice.getByRole("option", { name: /Dagua.*71.450.*2024/ }).click();
  const quote = map.locator('.map-price-popup article[data-selected-quote="true"]');
  await expect(map.locator(".map-price-popup article")).toHaveCount(7);
  await expect(quote).toBeFocused();
  await expect(quote).toContainText("31 de enero de 2024");
  await expect(quote.locator(".map-popup-price")).toBeInViewport();
  await expect(quote.getByRole("link", { name: "Consultar fuente", exact: true })).toBeInViewport();
  const href = new URL((await quote.getByRole("link", { name: "Consultar fuente", exact: true }).getAttribute("href"))!, "http://localhost");
  expect(href.pathname).toBe(`/evidence/${original}`);
  expect(href.searchParams.get("municipality")).toBe("Dagua");
  expect(href.searchParams.get("month")).toBe("2024-01-31");
  await choice.getByRole("combobox").fill("no-match-zzzz");
  await expect(quote).toContainText("Dagua, Valle del Cauca");
  await choice.getByRole("combobox").press("Escape");
  await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(map.locator(".map-price-popup article")).toHaveCount(6);
});
