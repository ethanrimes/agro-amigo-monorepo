import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import {
  cleanResult,
  waterfallRows,
  comparableProduct,
  type CleanInputs,
} from "../src/lib/cleansheet";
import { forecastValue } from "../src/lib/location-types";
const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
async function location(page: Page) {
  await page.addInitScript(() =>
    localStorage.setItem(
      "agroamigo-location-v1",
      JSON.stringify({
        point: { latitude: 1.9, longitude: -76.1 },
        name: "Mi pin",
        municipalityId: "41551",
      }),
    ),
  );
  await page.goto("/farm");
}
test("map layers, month, source viewer and saved pin work independently", async ({
  page,
  browserName,
}) => {
  test.setTimeout(150000);
  await location(page);
  const map = page.locator(".zone-map");
  await expect(map).toHaveAttribute("data-ready", "true");
  await expect(map).toHaveAttribute("data-pin-lat", "1.9");
  await expect
    .poll(async () => Number(await map.getAttribute("data-tiles")), {
      timeout: 60000,
    })
    .toBeGreaterThan(0);
  await page.getByLabel("Mes habitual", { exact: true }).selectOption("9");
  await expect(page.locator(".zone-reading").first()).toContainText(
    "50 - 100 mm",
    { timeout: 45000 },
  );
  await page.getByLabel("Mes habitual", { exact: true }).selectOption("1");
  await expect(page.locator(".zone-reading").first()).toContainText("Enero");
  await expect(
    page
      .locator(".zone-reading")
      .first()
      .getByRole("link", { name: "Ver valores originales y consulta exacta" }),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole("button", { name: "Suelos", exact: true }).click();
  await expect(map).toHaveAttribute("data-layer", "soil");
  await expect(page.locator(".zone-reading").first()).toContainText("Textura", {
    timeout: 45000,
  });
  await page
    .locator(".zone-reading")
    .first()
    .getByRole("link", { name: "Ver valores originales y consulta exacta" })
    .click();
  await expect(page.locator("dialog")).toBeVisible();
  await expect(page.locator(".evidence-heading")).toContainText("IGAC");
  await expect(page.locator(".evidence-records")).toContainText("Textura");
  await page
    .getByRole("button", { name: "Cerrar ventana", exact: true })
    .click();
  await map.scrollIntoViewIfNeeded();
  await map.click({ position: { x: 75, y: 140 } });
  await expect(
    page.getByRole("button", { name: "Fijar mi pin aquí" }),
  ).toBeVisible();
  await expect(map).toHaveAttribute("data-pin-lat", "1.9");
  const canvas = map.locator("canvas");
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + 130, box.y + 160);
  await page.mouse.down();
  await page.mouse.move(box.x + 190, box.y + 210, { steps: 5 });
  await page.mouse.up();
  await expect(map).toHaveAttribute("data-pin-lat", "1.9");
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("agroamigo-location-v1")!).point
          .latitude,
    ),
  ).toBe(1.9);
  await page.screenshot({
    path: `../../artifacts/location/soil-${browserName}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("cleansheet table and waterfall reconcile, retain assumptions between tabs and export sources", async ({
  page,
  browserName,
}) => {
  test.setTimeout(100000);
  await location(page);
  await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
  await page.getByRole("button", { name: "Mi precio", exact: true }).click();
  await page.getByLabel("Mi precio esperado (COP/kg)").fill("20000");
  await page.getByLabel("Área que quieres analizar (ha)").fill("2");
  await page.getByLabel("Rendimiento esperado (kg/ha)").fill("1000");
  await page.getByLabel("Pérdidas antes de vender (%)").fill("10");
  for (const label of [
    "Labores antes de cosecha",
    "Semilla e insumos",
    "Mano de obra de cosecha",
    "Otros rubros del total publicado",
  ])
    await page.getByLabel(label + " (COP/ha)", { exact: true }).fill("1000000");
  await page
    .getByLabel("Transporte, empaque y venta (COP totales)")
    .fill("500000");
  await page
    .getByLabel("Comisión sobre la venta (%)", { exact: true })
    .fill("5");
  await expect(page.locator(".clean-kpis")).toContainText(money(25700000));
  await expect(page.locator(".clean-kpis")).toContainText(money(36000000));
  await expect(page.locator(".clean-waterfall")).toBeVisible();
  await page.getByRole("button", { name: "Tabla", exact: true }).click();
  await expect(page.locator(".clean-result-table .total")).toContainText(
    money(25700000),
  );
  await page.getByRole("tab", { name: /Explorar mi zona/ }).click();
  await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
  await expect(page.getByLabel("Mi precio esperado (COP/kg)")).toHaveValue(
    "20000",
  );
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Descargar análisis con sus fuentes" })
    .click();
  expect((await downloaded).suggestedFilename()).toBe(
    "analisis-agroamigo.json",
  );
  await page.getByLabel("Mi precio esperado (COP/kg)").fill("1000");
  await expect(page.locator(".clean-kpis .loss")).toContainText(
    money(-6790000),
  );
  await page.getByRole("button", { name: "Cascada", exact: true }).click();
  await expect(page.locator(".clean-waterfall")).toContainText(
    "Pérdida estimada",
  );
  await page.locator(".clean-results").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `../../artifacts/location/cleansheet-${browserName}.png`,
  });
  await page.getByLabel("Labores antes de cosecha (COP/ha)").fill("");
  await expect(page.locator(".clean-results")).toContainText(
    "Completa los supuestos",
  );
  await expect(page.locator(".clean-kpis")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("regional UPRA cost comparison preserves source year and requires comparability confirmation", async ({
  page,
}) => {
  await location(page);
  await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
  await page
    .getByRole("combobox", { name: "Elegir cultivo para el análisis" })
    .fill("Frijol");
  await page
    .getByRole("option", { name: /Frijol/ })
    .first()
    .click();
  await expect(page.locator(".clean-template")).toContainText("2023");
  await page
    .getByRole("button", {
      name: "Usar costos del estudio como punto de partida",
    })
    .click();
  await expect(page.locator(".clean-comparison").first()).toContainText(
    "Activa la comparación",
  );
  await page.getByRole("checkbox", { name: /El sistema, período/ }).check();
  await page.getByLabel("Labores antes de cosecha (COP/ha)").fill("4000000");
  await expect(page.locator(".clean-comparison").first()).toContainText(
    "nominal",
  );
  await expect(page.locator(".clean-template .evidence-link")).toHaveAttribute(
    "href",
    /page=/,
  );
  await expect(page.locator(".clean-cost-panel")).toContainText(
    "no mide eficiencia",
  );
});
test("denied GPS leaves the map usable without inventing a pin", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "geolocation", {
      value: {
        getCurrentPosition: (
          _: unknown,
          error: (e: { code: number }) => void,
        ) => error({ code: 1 }),
      },
      configurable: true,
    }),
  );
  await page.goto("/farm");
  await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
  await expect(
    page.getByText("El permiso de ubicación está desactivado.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.locator(".zone-map")).not.toHaveAttribute(
    "data-pin-lat",
    /.+/,
  );
});
test("spatial evidence is archived, hashed and downloadable and invalid queries are rejected", async ({
  request,
}) => {
  const layers = await (await request.get("/api/location/layers")).json();
  expect(layers).toHaveLength(7);
  const response = await request.get(
    "/api/location/point?layer=rain-month&month=9&lat=1.9&lon=-76.1",
  );
  expect(response.ok()).toBeTruthy();
  const p = await response.json();
  expect(p.records[0].rangos).toBe("50 - 100 mm");
  const original = await request.get(`/api/evidence/${p.documentId}/content`);
  expect(original.ok()).toBeTruthy();
  expect(
    createHash("sha256")
      .update(await original.body())
      .digest("hex"),
  ).toBe(p.documentId.slice(8));
  const evidence = await (
    await request.get("/api/evidence/" + p.documentId)
  ).json();
  expect(evidence.parents).toHaveLength(1);
  expect(evidence.publisher).toBe("IDEAM");
  expect(
    (
      await request.get(
        "/api/location/point?layer=rain-month&month=13&lat=1.9&lon=-76.1",
      )
    ).status(),
  ).toBe(400);
  expect(
    (await request.get("/api/location/grid?lat=90&lon=0&step=0.25")).status(),
  ).toBe(400);
});
test("financial identities, losses, missing costs and forecast missingness are explicit", () => {
  const inputs: CleanInputs = {
    area: "2",
    yieldKg: "1000",
    loss: "10",
    price: "20000",
    commission: "5",
    delivery: "500000",
    costs: [{ label: "Producción", amount: "4000000", timing: "before" }],
  };
  const result = cleanResult(inputs)!;
  expect(result.profit).toBe(25700000);
  expect(result.breakEven).toBeCloseTo(4970.7602339);
  expect(waterfallRows(inputs).at(-1)?.end).toBe(result.profit);
  expect(cleanResult({ ...inputs, commission: "100" })).toBeNull();
  expect(
    cleanResult({ ...inputs, costs: [{ ...inputs.costs[0], amount: "" }] }),
  ).toBeNull();
  expect(cleanResult({ ...inputs, price: "1000" })?.profit).toBe(-6790000);
  expect(comparableProduct("Caña", "Panela")).toBe(false);
  expect(comparableProduct("Arroz", "Arroz de primera")).toBe(false);
  const sample = {
    latitude: 1,
    longitude: -76,
    modelLatitude: 1,
    modelLongitude: -76,
    dates: ["a", "b"],
    rain: [4, null],
    low: [15, 16],
    high: [22, 23],
    wind: [10, 10],
  };
  expect(forecastValue(sample, "rain", null)).toBeNull();
  expect(forecastValue(sample, "rain", 0)).toBe(4);
  expect(forecastValue(sample, "risk", null)).toBeNull();
  expect(forecastValue({ ...sample, rain: [4, 25] }, "risk", null)).toBe(1);
});
test("forecast map is explorable, dated and distinguished from historic climate and official alerts", async ({
  page,
}) => {
  test.setTimeout(100000);
  await location(page);
  await page.getByLabel("Horizonte de la información").selectOption("forecast");
  await expect
    .poll(
      async () =>
        Number(await page.locator(".zone-map").getAttribute("data-points")),
      { timeout: 45000 },
    )
    .toBeGreaterThan(0);
  await expect(page.locator(".zone-map-caption")).toContainText(
    "Lluvia acumulada",
  );
  await expect(page.locator(".zone-provenance")).toContainText(
    "no es una medición continua",
  );
  await expect(page.locator(".zone-provenance .evidence-link")).toBeVisible();
  await page.getByLabel("Días del pronóstico").selectOption("0");
  await page
    .getByRole("button", { name: "Tiempo severo", exact: true })
    .click();
  await expect(page.locator(".zone-provenance")).toContainText(
    "no alertas oficiales",
  );
  await expect(page.locator(".zone-legend")).toContainText(
    "Revisar condiciones",
  );
  await page.getByRole("button", { name: "Lluvia", exact: true }).click();
  await page.getByLabel("Horizonte de la información").selectOption("year");
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-layer",
    "rain-year",
  );
  await expect(page.locator(".zone-map-caption")).toContainText("1991–2020");
  await expect(page.locator(".zone-reading").first()).toContainText("mm/año");
});
test("GPS pin persists and old farm records are preserved in the informational workspace", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({
    latitude: 1.9,
    longitude: -76.1,
    accuracy: 12,
  });
  await page.addInitScript(() => {
    if (sessionStorage.getItem("legacy-farm-seeded")) return;
    sessionStorage.setItem("legacy-farm-seeded", "1");
    localStorage.setItem(
      "agroamigo-farms-v2",
      JSON.stringify({
        version: 2,
        activeId: "old-farm",
        farms: [
          {
            id: "old-farm",
            profile: {
              name: "La Esperanza",
              municipalityId: "41551",
              area: "3",
              latitude: "1.85",
              longitude: "-76.05",
            },
            crops: [],
            selectedCropId: "",
          },
        ],
      }),
    );
  });
  await page.goto("/farm/old-farm");
  await expect(page.locator(".location-place")).toContainText("La Esperanza");
  await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lat",
    "1.9",
  );
  const saved = await page.evaluate(() => localStorage.getItem("agroamigo-farms-v2"));
  const profile = JSON.parse(saved!).farms[0].profile;
  expect(profile).toMatchObject({
    name: "La Esperanza", municipalityId: "41551", area: "3",
    locationMethod: "gps",
  });
  expect(Number(profile.latitude)).toBeCloseTo(1.9, 6);
  expect(Number(profile.longitude)).toBeCloseTo(-76.1, 6);
  await page.goto("/farm");
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lat",
    "1.9",
  );
  expect(
    await page.evaluate(() => localStorage.getItem("agroamigo-farms-v2")),
  ).toBe(saved);
});
