import { test, expect, type Page } from "@playwright/test";
import { EMPTY_PROFILE } from "../src/lib/farm-types";

async function seed(page: Page, pinned = false) {
  await page.addInitScript(
    ({ profile, pinned }) => {
      if (sessionStorage.getItem("farm-pin-test-seeded")) return;
      sessionStorage.setItem("farm-pin-test-seeded", "yes");
      localStorage.setItem(
        "agroamigo-farms-v2",
        JSON.stringify({
          version: 2,
          activeId: "farm-exact",
          farms: [
            {
              id: "farm-exact",
              profile: {
                ...profile,
                name: "La Esperanza",
                municipalityId: "41551",
                latitude: pinned ? "1.912345" : "",
                longitude: pinned ? "-76.123456" : "",
                locationMethod: pinned ? "manual" : "",
              },
              crops: [
                {
                  id: "coffee-plan",
                  area: "1",
                  budget: { name: "Presupuesto conservado" },
                },
              ],
              selectedCropId: "coffee-plan",
            },
          ],
        }),
      );
      localStorage.setItem(
        "agroamigo-location-v1",
        JSON.stringify({
          point: pinned ? { latitude: 1.9, longitude: -76.1 } : null,
          municipalityId: "41551",
          name: "Antigua exploración",
        }),
      );
    },
    { profile: EMPTY_PROFILE, pinned },
  );
  await page.goto("/farm");
  await expect(page.locator(".zone-map")).toBeVisible();
}

test("municipal references never create a farm pin; GPS location persists in the farm", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 1.912345, longitude: -76.123456, accuracy: 8 });
  await seed(page);
  const map = page.locator(".zone-map");
  await expect(map).not.toHaveAttribute("data-pin-lat");
  await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
  await expect(map).toHaveAttribute("data-pin-lat", "1.912345");
  await expect(map).toHaveAttribute("data-pin-lon", "-76.123456");
  await expect(page.locator(".location-place")).toContainText(
    "GPS · precisión aproximada ±8 m",
  );
  const stored = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("agroamigo-farms-v2")!),
  );
  expect(stored.farms[0].profile).toMatchObject({
    latitude: "1.912345",
    longitude: "-76.123456",
    locationMethod: "gps",
    municipalityId: "41551",
  });
  expect(stored.farms[0].crops[0].budget.name).toBe("Presupuesto conservado");
  await page.reload();
  await expect(map).toHaveAttribute("data-pin-lat", "1.912345");
  const search = page.getByRole("combobox", {
    name: "Buscar municipio",
    exact: true,
  });
  await search.fill("Pitalito");
  await page
    .getByRole("option", { name: /Pitalito/i })
    .first()
    .click();
  await expect(map).toHaveAttribute("data-pin-lat", "1.912345");
  await expect(page.locator(".location-message")).toContainText(
    "La selección no cambia tu pin",
  );
  expect(
    await page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("agroamigo-farms-v2")!).farms[0]
          .crops[0].budget.name,
    ),
  ).toBe("Presupuesto conservado");
});

test("an old municipal exploration cannot override a saved farm point and weather uses farm coordinates", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const weather: URL[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/planning/weather?"))
      weather.push(new URL(request.url()));
  });
  await seed(page, true);
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lat",
    "1.912345",
  );
  await expect(page.locator(".location-place")).toContainText("La Esperanza");
  const previous = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("agroamigo-location-legacy-v1")!),
  );
  expect(previous.point.latitude).toBe(1.9);
  await expect
    .poll(() =>
      weather.some(
        (url) =>
          url.searchParams.get("lat") === "1.912345" &&
          url.searchParams.get("lon") === "-76.123456",
      ),
    )
    .toBeTruthy();
  await page.reload();
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lon",
    "-76.123456",
  );
});

test("GPS saves the precise point and an out-of-coverage GPS reading preserves it", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({
    latitude: 1.923456,
    longitude: -76.134567,
    accuracy: 8,
  });
  await seed(page, true);
  await page
    .getByRole("button", { name: "Usar mi ubicación", exact: true })
    .click();
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lat",
    "1.923456",
  );
  await expect(page.locator(".location-place")).toContainText(
    "GPS · precisión aproximada ±8 m",
  );
  await context.setGeolocation({ latitude: 70, longitude: -76, accuracy: 8 });
  await page.getByRole("button", { name: "Usar mi ubicación", exact: true }).click();
  await expect(page.locator(".location-message")).toContainText("fuera del área");
  await expect(page.locator(".zone-map")).toHaveAttribute(
    "data-pin-lat",
    "1.923456",
  );
  const stored = await page.evaluate(
    () =>
      JSON.parse(localStorage.getItem("agroamigo-farms-v2")!).farms[0].profile,
  );
  expect(stored).toMatchObject({
    latitude: "1.923456",
    longitude: "-76.134567",
    locationAccuracy: "8",
    locationMethod: "gps",
  });
});
