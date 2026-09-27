import { test, expect, type Page } from "@playwright/test";

const municipality = {
  id: "41551",
  name: "Pitalito",
  department: "Huila",
  department_id: "41",
  latitude: 1.9,
  longitude: -76.1,
  document_id: "fixture-location",
};
const crop = {
  crop_code: "frijol",
  crop: "Frijol",
  variety: "Frijol seco",
  reference_year: 2025,
  cycle: "Transitorio",
  physical_state: "Grano seco",
  planted_ha: 15,
  harvested_ha: 12,
  production_t: 18,
  yield_kg_ha: 1500,
  document_id: "fixture-eva",
  source_rows: [42],
};
const coffee = {
  ...crop,
  crop_code: "cafe",
  crop: "Café",
  variety: "Café",
  physical_state: "Pergamino seco",
  cycle: "Permanente",
};
const data = {
  municipality,
  crops: [crop, coffee],
  calendars: [
    {
      crop: "Frijol",
      activity: "Siembra",
      percentages: [2, 3, 5, 10, 10, 20, 15, 10, 5, 5, 5, 10],
      reference_year: 2024,
      document_id: "fixture-calendar",
      source_row: 17,
    },
  ],
  suitability: [],
  soil: null,
  advisories: [],
  templates: [
    {
      id: "frijol-study",
      crop: "Frijol",
      title: "Frijol tecnificado",
      region: "Estudio Huila",
      municipalities: ["41551"],
      reference_year: 2023,
      production_system: "Secano · ciclo",
      yield_kg_ha: 1400,
      costs: [
        { label: "Semilla", amount: 350000, timing: "before" },
        { label: "Cosecha", amount: 125000.5, timing: "harvest" },
      ],
      document_id: "fixture-cost",
      source_page: 13,
      notes:
        "Precios nominales del estudio. La asignación del momento de pago es editable; no proviene de un calendario financiero de UPRA.",
    },
  ],
};
const profile = {
  municipalityId: "41551",
  name: "Mi finca conservada",
  cropCode: "frijol",
  variety: "Frijol seco",
  area: "2",
  stage: "harvest",
  plantingDate: "2025-11-10",
  floweringDate: "2026-02-01",
  irrigation: false,
  latitude: "1.9",
  longitude: "-76.1",
  elevation: "1800",
  locationMethod: "manual",
  locationAccuracy: "",
};
const oldBudget = {
  label: "Preservar importes privados",
  revenue: 123456,
  priceMode: "manual",
  manualPrice: "2011.35",
  sourceDocuments: ["original-old-id"],
  costsPerHa: [{ label: "Mi costo", amount: 12987, timing: "before" }],
};
const store = {
  version: 2,
  activeId: "farm-a",
  farms: [
    {
      id: "farm-a",
      profile,
      selectedCropId: "crop-a",
      crops: [
        {
          id: "crop-a",
          cropCode: "frijol",
          name: "Frijol",
          variety: "Frijol seco",
          physicalState: "Grano seco",
          area: "2",
          yieldKgHa: "1234",
          budget: oldBudget,
        },
      ],
    },
    {
      id: "farm-b",
      profile: { ...profile, name: "Otra finca", municipalityId: "41001" },
      selectedCropId: "crop-b",
      crops: [
        {
          id: "crop-b",
          cropCode: "cafe",
          name: "Café",
          area: "1",
          budget: { ...oldBudget, manualPrice: "4000" },
        },
      ],
    },
  ],
};
const original = {
  "agroamigo-farms-v2": JSON.stringify(store, null, 2),
  "agroamigo-scenarios-farm-a": JSON.stringify([oldBudget], null, 2),
  "agroamigo-scenarios-v1": '[{"legacy":true,"price":18.45}]',
  "agroamigo-location-v1": JSON.stringify({
    version: 2,
    farmId: "farm-a",
    point: { latitude: 1.9, longitude: -76.1 },
    name: profile.name,
    municipalityId: "41551",
    method: "manual",
  }),
  "agroamigo-location-legacy-v1": '{"old":"kept verbatim"}',
};
async function fixtures(page: Page, years = 3) {
  await page.addInitScript((values) => {
    if (!sessionStorage.getItem("qa-reference-seeded")) {
      for (const [k, v] of Object.entries(values)) localStorage.setItem(k, v);
      sessionStorage.setItem("qa-reference-seeded", "1");
    }
  }, original);
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname === "/api/planning/municipalities")
      return route.fulfill({
        json: [municipality, { ...municipality, id: "41001", name: "Neiva" }],
      });
    if (u.pathname === "/api/planning/farm")
      return route.fulfill({
        json: {
          ...data,
          municipality:
            u.searchParams.get("id") === "41001"
              ? { ...municipality, id: "41001", name: "Neiva" }
              : municipality,
        },
      });
    if (u.pathname === "/api/catalog")
      return route.fulfill({
        json: {
          products: [
            {
              id: "frijol-rojo",
              name: "Frijol rojo seco",
              kind: "product",
              currency: "COP",
              unit: "kg",
              series: "monthly",
            },
          ],
        },
      });
    if (u.pathname === "/api/products/frijol-rojo")
      return route.fulfill({
        json: {
          markets: [
            {
              id: "test-market",
              name: "Mercado de prueba",
              unit: "kg",
              price: 3000,
              document_id: "fixture-latest",
            },
          ],
        },
      });
    if (u.pathname === "/api/planning/seasonality")
      return route.fulfill({
        json: {
          unit:
            u.searchParams.get("product") === "cafe-pergamino-seco"
              ? "kg de pergamino seco"
              : "kg",
          latest: {
            price: 3000,
            date: "2026-08-31",
            market: "Mercado de prueba",
          },
          method: "Precios mensuales observados.",
          years: Array.from({ length: years }, (_, i) => ({
            reference_year: 2023 + i,
            monthly_prices: Array.from(
              { length: 12 },
              (_, m) => 2000 + i * 100 + m * 10,
            ),
            document_id: "fixture-history-" + i,
            source_rows: Array(12).fill("Fila original"),
            source_documents: Array.from({ length: 12 }, (_, m) => [
              "fixture-history-" + i + "-" + m,
            ]),
          })),
        },
      });
    if (u.pathname === "/api/evidence/coffee-cost-benchmark")
      return route.fulfill({
        json: {
          id: "coffee-cost-benchmark",
          metadata: { cost_per_125kg: 1550805 },
        },
      });
    return route.fulfill({
      status: 503,
      json: { error: "No fixture for unrelated service" },
    });
  });
}
async function unchanged(page: Page) {
  expect(
    await page.evaluate(
      (keys) =>
        Object.fromEntries(keys.map((k) => [k, localStorage.getItem(k)])),
      Object.keys(original),
    ),
  ).toEqual(original);
}

test("old farm, crop and budget bytes survive informational navigation and reload", async ({
  page,
}) => {
  await fixtures(page);
  await page.goto("/farm");
  await expect(
    page.getByRole("heading", { name: "Explorar mi zona" }),
  ).toBeVisible();
  await expect(
    page.locator("#clean-tab,#clean-panel,.clean-sheet,.budget-layout"),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "¿Qué se cultiva en este municipio?" })
    .click();
  await page
    .getByRole("link", { name: "Ver calendario y fuentes" })
    .first()
    .click();
  await expect(page.locator(".crop-references h2").first()).toHaveText(
    "Frijol seco",
  );
  await page.getByLabel("Municipio de referencia").selectOption("41001");
  await expect(page.locator(".crop-references .eyebrow").first()).toContainText(
    "Neiva",
  );
  await unchanged(page);
  await page.reload();
  await expect(page.locator(".crop-references")).toBeVisible();
  await page.getByRole("link", { name: "Volver a Mi finca" }).click();
  await expect(page.locator(".location-place strong")).toHaveText(profile.name);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await unchanged(page);
});

test("old budget deep link exposes exact public calendar/cost rows and source locators without calculator", async ({
  page,
}, info) => {
  await fixtures(page);
  await page.goto("/plan?tab=budget&farm=farm-a&crop=crop-a");
  await expect(
    page.getByRole("heading", { name: "Cultivos, calendarios y fuentes" }),
  ).toBeVisible();
  await expect(
    page.getByText("Este enlace ahora muestra las referencias publicadas.", {
      exact: false,
    }),
  ).toBeVisible();
  const row = page.locator(".calendar-table tbody tr");
  await expect(row.locator("th")).toHaveText("Siembra · 2024");
  await expect(
    row.locator("td").filter({ hasNot: page.locator("a") }),
  ).toHaveText(data.calendars[0].percentages.map(String));
  await expect(row.locator("a")).toHaveAttribute(
    "href",
    "/evidence/fixture-calendar?department=41",
  );
  await page.locator(".published-cost-references summary").click();
  await expect(page.locator(".published-cost-references")).not.toContainText(
    "es editable",
  );
  await expect(page.locator(".published-cost-references tbody td")).toHaveText([
    "$ 350.000",
    "$ 125.001",
  ]);
  await expect(
    page.locator(".published-cost-references tfoot td"),
  ).toContainText("475.001");
  await expect(
    page.locator(".published-cost-references .evidence-link"),
  ).toHaveAttribute("href", "/evidence/fixture-cost?page=13");
  await expect(page.locator(".published-cost-references")).toContainText(
    "2023",
  );
  await expect(
    page.locator(
      "input[type=number],input[type=date],.break-even,.earnings-scenarios,.clean-kpis",
    ),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("read-only-references.png"),
    fullPage: true,
  });
  await unchanged(page);
});

test("incomplete seasonal population retains all literal monthly rows and sources without forecasting", async ({
  page,
}) => {
  await fixtures(page, 2);
  await page.goto("/plan?tab=budget&farm=farm-a&crop=crop-a");
  await page
    .getByText("Consultar historia y estacionalidad de precios", {
      exact: true,
    })
    .click();
  await expect(page.locator(".seasonal-panel")).toContainText(
    "No hay al menos 3 años completos",
  );
  await expect(page.locator(".seasonal-bars")).toHaveCount(0);
  await page
    .getByText("Ver precios históricos y método", { exact: true })
    .click();
  await expect(page.locator(".seasonal-panel tbody tr")).toHaveCount(2);
  await expect(
    page.locator(".seasonal-panel tbody tr").first().locator("td").first(),
  ).toContainText("2.000");
  await expect(
    page
      .locator(".seasonal-panel tbody tr")
      .first()
      .locator("td")
      .first()
      .locator("a"),
  ).toHaveAttribute("href", "/evidence/fixture-history-0-0");
  await expect(
    page.locator(".seasonal-panel tbody tr").last().locator("td").nth(11),
  ).toContainText("2.210");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await unchanged(page);
});

test("unknown saved farm/crop never substitutes another farm or rewrites saved data", async ({
  page,
}) => {
  await fixtures(page);
  await page.goto("/plan?tab=budget&farm=missing");
  await expect(
    page.getByRole("heading", {
      name: "No encontramos esa finca en este dispositivo",
    }),
  ).toBeVisible();
  await expect(page.locator(".crop-references")).toHaveCount(0);
  await unchanged(page);
  await page.goto("/plan?farm=farm-a&crop=missing");
  await expect(
    page.getByText("No hay una referencia EVA", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".crop-references")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await unchanged(page);
});

test("reference failure is visible and retry restores crop access without touching stored farms", async ({
  page,
}) => {
  await fixtures(page);
  let fail = true;
  await page.route("**/api/planning/farm?*", (route) =>
    fail
      ? route.fulfill({
          status: 503,
          json: { error: "Reference fixture unavailable" },
        })
      : route.fulfill({ json: data }),
  );
  await page.goto("/farm");
  const failure = page
    .getByRole("alert")
    .filter({ hasText: "Reference fixture unavailable" });
  await expect(failure).toBeVisible();
  await unchanged(page);
  fail = false;
  await failure.getByRole("button", { name: "Volver a intentar" }).click();
  await expect(
    page.getByRole("button", { name: "¿Qué se cultiva en este municipio?" }),
  ).toBeVisible();
  await expect(failure).toHaveCount(0);
  await unchanged(page);
});
