import { test, expect, type Page } from "@playwright/test";

const municipality = {
  id: "41551",
  name: "Pitalito",
  department: "Huila",
  department_id: "41",
  latitude: 1.9,
  longitude: -76.1,
  document_id: "fixture",
};
const farm = {
  municipality,
  crops: [
    {
      crop_code: "frijol",
      crop: "Frijol",
      variety: "Frijol",
      reference_year: 2025,
      cycle: "Transitorio",
      physical_state: "Grano seco",
      planted_ha: 1,
      harvested_ha: 1,
      production_t: 1,
      yield_kg_ha: 1000,
      document_id: "fixture",
      source_rows: [1],
    },
  ],
  calendars: [],
  suitability: [],
  soil: null,
  templates: [],
  advisories: [],
};
const local = {
  id: "frijol-rojo",
  identity: "frijol-rojo",
  saved_key: "frijol-rojo",
  name: "Frijol rojo local",
  category: "Granos",
  image_key: "produce",
  price: 5000,
  previous_price: null,
  date: "2026-08-31",
  market_count: 1,
  unit: "kg",
  currency: "COP",
  source: "DANE SIPSA",
  period: "monthly",
  series: "monthly",
  kind: "product",
  basis: "Promedio mensual mayorista",
  presentation: "Kilogramo",
  units: "1 Kilogramo",
  href: "/product/frijol-rojo",
  market: "Colombia",
  map_supported: true,
  search_terms: ["Frijol"],
};
const unsupported = [
  { currency: "USD" },
  { unit: "tonne" },
  { unit: "pack" },
  { kind: "official-reference" },
  { series: "city" },
  { series: "mill" },
  { currency: null },
  { unit: "litre" },
].map((overrides, index) => ({
  ...local,
  id: "unsupported-" + index,
  identity: "unsupported-" + index,
  name: "Frijol referencia " + index,
  ...overrides,
}));

async function fixtures(page: Page, historyUnit: string) {
  const seasonalityRequests: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem(
      "agroamigo-farm-v1",
      JSON.stringify({
        municipalityId: "41551",
        name: "Prueba",
        cropCode: "frijol",
        variety: "Frijol",
        area: "1",
        stage: "harvest",
        plantingDate: "",
        floweringDate: "",
        irrigation: false,
        latitude: "1.9",
        longitude: "-76.1",
        elevation: "1800",
      }),
    );
    localStorage.setItem(
      "agroamigo-location-v1",
      JSON.stringify({
        point: { latitude: 1.9, longitude: -76.1 },
        municipalityId: "41551",
        name: "Prueba",
      }),
    );
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const json = async (body: unknown) => route.fulfill({ json: body });
    if (url.pathname === "/api/planning/municipalities")
      return json([municipality]);
    if (url.pathname === "/api/planning/farm") return json(farm);
    if (url.pathname === "/api/catalog")
      return json({
        products: [...unsupported, local],
        regions: [],
        latestDate: local.date,
      });
    if (url.pathname.startsWith("/api/products/")) {
      expect(url.pathname).toBe("/api/products/frijol-rojo");
      expect(url.searchParams.get("series")).toBe("monthly");
      return json({
        markets: [
          {
            id: "unsupported-package",
            name: "A Empaque",
            region: "Huila",
            unit: "pack",
            price: 50000,
          },
          {
            id: "safe-market",
            name: "Mercado COP/kg",
            region: "Huila",
            unit: "kg",
            price: 5000,
          },
        ],
      });
    }
    if (url.pathname === "/api/planning/seasonality") {
      seasonalityRequests.push(url.search);
      expect(url.searchParams.get("product")).toBe("frijol-rojo");
      expect(url.searchParams.get("market")).toBe("safe-market");
      return json({
        unit: historyUnit,
        latest: { price: 5000, date: "2026-08-31", market: "Mercado COP/kg" },
        years: [2023, 2024, 2025].map((reference_year) => ({
          reference_year,
          monthly_prices: Array(12).fill(5000),
          document_id: "fixture",
          source_rows: [],
        })),
        method: "Fixture for price-basis compatibility",
      });
    }
    return route.fulfill({
      status: 503,
      json: { error: "Unrelated service omitted from this focused fixture" },
    });
  });
  return seasonalityRequests;
}

for (const surface of ["budget", "cleansheet"] as const) {
  for (const unit of ["kg", "pack"]) {
    test(`${surface} excludes incompatible unified catalog quotes and ${unit === "kg" ? "retains COP/kg history" : "rejects package history"}`, async ({
      page,
    }) => {
      const requests = await fixtures(page, unit);
      await page.goto(surface === "budget" ? "/plan?tab=budget" : "/farm");
      if (surface === "cleansheet")
        await page.getByRole("tab", { name: /Costos y rentabilidad/ }).click();
      const picker = page.getByLabel(
        surface === "budget"
          ? "Producto y presentación que venderías"
          : "Producto comparable",
      );
      await expect(picker).toHaveValue("frijol-rojo");
      await expect(picker.locator("option")).toHaveText([
        surface === "budget" ? "Selecciona una presentación" : "Sin selección",
        "Frijol rojo local",
      ]);
      await expect(
        page.getByRole("combobox", {
          name: "Mercado de referencia",
          exact: true,
        }),
      ).toHaveValue("safe-market");
      await expect.poll(() => requests.length).toBeGreaterThan(0);
      if (unit === "kg") {
        await expect(page.locator(".seasonal-bars button")).toHaveCount(12);
        if (surface === "cleansheet")
          await expect(page.locator(".clean-price b")).toContainText("5.000");
      } else {
        await expect(page.locator(".seasonal-bars")).toHaveCount(0);
        if (surface === "cleansheet")
          await expect(page.locator(".clean-price")).toHaveCount(0);
        else
          await expect(
            page.getByText(
              "La referencia disponible no corresponde al precio por kg",
              { exact: false },
            ),
          ).toBeVisible();
      }
    });
  }
}
