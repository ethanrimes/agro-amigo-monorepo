import { test, expect, type Page } from "@playwright/test";
import { EMPTY_PROFILE } from "../src/lib/farm-types";
import { currentWeatherIsOld, hasCurrentWeather, weatherTime } from "../src/lib/weather-data";
import type { Weather } from "../src/lib/planning-types";

function fixture(stale = false): Weather {
  const now = new Date(), start = new Date(now.getTime() - now.getTime() % 3600_000);
  const local = (date: Date) => new Date(date.getTime() - 5 * 3600_000).toISOString().slice(0, 19);
  const times = Array.from({ length: 168 }, (_, i) => local(new Date(start.getTime() + i * 3600_000)));
  const days = Array.from({ length: 7 }, (_, i) => local(new Date(start.getTime() + i * 86400_000)).slice(0, 10));
  return { id: "fixture-weather", latitude: 1.912345, longitude: -76.123456,
    fetched_at: new Date(now.getTime() - (stale ? 2 * 3600_000 : 0)).toISOString(), stale,
    source_url: "https://api.open-meteo.com/v1/forecast", payload: {
      latitude: 1.91, longitude: -76.12, elevation: 1300, timezone: "America/Bogota",
      current: { time: local(now), interval: 900, temperature_2m: 23.4, apparent_temperature: 24,
        relative_humidity_2m: 82, precipitation: 0, weather_code: 2, wind_speed_10m: 8, wind_gusts_10m: 13, is_day: 1 },
      current_units: { temperature_2m: "°C", precipitation: "mm", wind_speed_10m: "km/h", relative_humidity_2m: "%" },
      hourly: { time: times, temperature_2m: times.map(() => 24), precipitation: times.map(() => 1.3),
        precipitation_probability: times.map(() => 65), weather_code: times.map(() => 61), wind_speed_10m: times.map(() => 10) },
      hourly_units: { temperature_2m: "°C", precipitation_probability: "%", wind_speed_10m: "km/h", precipitation: "mm" },
      daily: { time: days, weather_code: days.map(() => 61), temperature_2m_max: days.map(() => 27), temperature_2m_min: days.map(() => 17),
        precipitation_sum: days.map(() => 5), precipitation_probability_max: days.map(() => 80), wind_speed_10m_max: days.map(() => 18), et0_fao_evapotranspiration: days.map(() => 3) },
      daily_units: { precipitation_sum: "mm" },
    } };
}
async function seed(page: Page) {
  await page.addInitScript(profile => {
    if (sessionStorage.getItem("weather-test-seeded")) return;
    sessionStorage.setItem("weather-test-seeded", "1");
    localStorage.setItem("agroamigo-farms-v2", JSON.stringify({ version: 2, activeId: "weather-farm", farms: [{
      id: "weather-farm", profile: { ...profile, name: "La Esperanza", latitude: "1.912345", longitude: "-76.123456", locationMethod: "pin" }, crops: [], selectedCropId: "",
    }] }));
  }, EMPTY_PROFILE);
  await page.route("**/api/planning/municipalities", route => route.fulfill({ json: [{ id: "41551", name: "Pitalito", department: "Huila", latitude: 1.85, longitude: -76.05 }] }));
  await page.route("**/api/location/layers", route => route.fulfill({ json: [] }));
  await page.route("**/api/location/search?**", route => route.fulfill({ json: { places: [{ id: "osm-1", name: "Corabastos", detail: "Bogotá · Mercado", latitude: 4.631, longitude: -74.161 }] } }));
}

test("weather validates units and marks model conditions stale with explicit Colombia times", () => {
  const w = fixture();
  expect(hasCurrentWeather(w.payload)).toBe(true);
  expect(currentWeatherIsOld(w)).toBe(false);
  expect(currentWeatherIsOld(fixture(true))).toBe(true);
  expect(weatherTime("2026-09-08T06:00").toISOString()).toBe("2026-09-08T11:00:00.000Z");
  w.payload.current_units!.temperature_2m = "°F";
  expect(hasCurrentWeather(w.payload)).toBe(false);
});

test("farm weather shows hourly/daily forecast, provenance and stale recovery without page overflow", async ({ page }, info) => {
  await seed(page);
  let stale = true;
  await page.route("**/api/planning/weather?**", route => route.fulfill({ json: fixture(stale) }));
  await page.goto("/farm");
  const weather = page.getByRole("region", { name: "Tiempo y pronóstico de mi finca" });
  await expect(weather).toContainText("Datos sin actualizar");
  await expect(weather).toContainText("23,4 °C");
  await expect(weather.getByRole("region", { name: /Pronóstico por hora/ }).locator("article")).toHaveCount(24);
  await weather.getByRole("button", { name: "Próximos 7 días", exact: true }).click();
  await expect(weather).toContainText("Hoy");
  await expect(weather.locator("article")).toHaveCount(7);
  await expect(weather.getByRole("link", { name: "Ver datos y unidades guardados en Azure" })).toHaveAttribute("href", "/evidence/weather-fixture-weather");
  await expect(weather.getByRole("link", { name: "Descargar datos" })).toHaveAttribute("href", "/api/evidence/weather-fixture-weather/content");
  stale = false;
  await weather.getByRole("button", { name: "Actualizar tiempo" }).click();
  await expect(weather).not.toContainText("Datos sin actualizar");
  await expect(weather).toContainText("Ahora · estimación del modelo");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await weather.screenshot({ path: info.outputPath("weather.png") });
  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute("content", /user-scalable=no/);
});

test("map and GPS replace typed coordinates; searching never changes the saved farm", async ({ page, context }) => {
  await seed(page);
  const requests: string[] = [];
  await page.route("**/api/planning/weather?**", route => { requests.push(route.request().url()); return route.fulfill({ json: fixture() }); });
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 2.33, longitude: -75.88, accuracy: 15 });
  await page.goto("/farm");
  await expect(page.getByRole("region", { name: "Tiempo y pronóstico de mi finca" })).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: /Latitud|Longitud/ })).toHaveCount(0);
  await expect(page.getByText(/Ingresar las coordenadas|Ajustar las coordenadas/)).toHaveCount(0);
  const search = page.getByRole("combobox", { name: "Buscar un lugar en el mapa" });
  await search.fill("Corabastos");
  await page.getByRole("option", { name: /Corabastos/ }).click();
  await expect(page.locator(".zone-map")).toHaveAttribute("data-pin-lat", "1.912345");
  await expect(page.getByRole("button", { name: "Fijar mi pin aquí" })).toBeVisible();
  expect(requests.every(url => new URL(url).searchParams.get("lat") === "1.912345")).toBe(true);
  await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
  await expect(page.locator(".zone-map")).toHaveAttribute("data-pin-lat", "2.33");
  await expect.poll(() => requests.some(url => new URL(url).searchParams.get("lat") === "2.33")).toBe(true);
  await page.reload();
  await expect(page.locator(".zone-map")).toHaveAttribute("data-pin-lat", "2.33");
  await expect(page.locator(".zone-map")).toHaveAttribute("data-ready", "true");
  const scale = page.locator(".zone-map .maplibregl-ctrl-scale");
  await expect(scale).toContainText(/m/);
  const before = await scale.textContent();
  await page.locator(".zone-map .maplibregl-ctrl-zoom-in").click();
  await expect(scale).not.toHaveText(before!);
  expect(await page.evaluate(() => window.visualViewport?.scale)).toBe(1);
});

test("sources have visible link styling and input catalog has no period selector", async ({ page }, info) => {
  await page.route("**/api/catalog**", route => route.fulfill({ json: { products: [], regions: [], latestDate: null } }));
  await page.route("**/api/planning/municipalities", route => route.fulfill({ json: [] }));
  await page.route("**/api/planning/inputs?**", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Conocer las fuentes" })).toHaveCSS("text-decoration-line", "underline");
  const footer = page.getByRole("contentinfo");
  await expect(footer.getByRole("link", { name: "Fuentes y ayuda" })).toHaveCSS("text-decoration-line", "underline");
  const credits = footer.getByRole("link", { name: "Créditos de imágenes" });
  await credits.scrollIntoViewIfNeeded();
  if (await page.getByRole("navigation", { name: "Navegación móvil" }).isVisible()) {
    const link = await credits.boundingBox(), nav = await page.getByRole("navigation", { name: "Navegación móvil" }).boundingBox();
    expect(link!.y + link!.height).toBeLessThanOrEqual(nav!.y);
  }
  await footer.screenshot({ path: info.outputPath("sources-footer.png") });
  await page.goto("/insumos?history=all");
  await expect(page.getByRole("heading", { name: "Insumos agropecuarios" })).toBeVisible();
  await expect(page.getByText("Período", { exact: true })).toHaveCount(0);
  await expect(page.locator("select option").filter({ hasText: /12 meses|histórico/ })).toHaveCount(0);
});
