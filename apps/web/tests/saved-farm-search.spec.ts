import { test, expect } from "@playwright/test";
import { EMPTY_PROFILE } from "../src/lib/farm-types";

test("searching saved farms keeps the active pin until an exact farm is chosen", async ({ page }) => {
  await page.addInitScript((profile) => {
    localStorage.setItem("agroamigo-farms-v2", JSON.stringify({
      version: 2,
      activeId: "farm-one",
      farms: [
        { id: "farm-one", profile: { ...profile, name: "La Esperanza", municipalityId: "41551", latitude: "1.912345", longitude: "-76.123456", locationMethod: "pin" }, crops: [], selectedCropId: "" },
        { id: "farm-two", profile: { ...profile, name: "La Esperanza Alta", municipalityId: "11001", latitude: "4.631000", longitude: "-74.161000", locationMethod: "pin" }, crops: [], selectedCropId: "" },
      ],
    }));
  }, EMPTY_PROFILE);
  await page.route("**/api/planning/municipalities", (route) => route.fulfill({ json: [
    { id: "41551", name: "Pitalito", department: "Huila", latitude: 1.85, longitude: -76.05 },
    { id: "11001", name: "Bogotá", department: "Bogotá D.C.", latitude: 4.63, longitude: -74.16 },
  ] }));
  await page.route("**/api/location/layers", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/planning/weather?**", (route) => route.fulfill({ status: 503, json: { error: "fixture" } }));

  await page.goto("/farm");
  const selector = page.getByRole("group", { name: "Finca guardada" });
  await expect(selector).toHaveAttribute("data-selected-value", "farm-one");
  await expect(selector).toContainText("La Esperanza");
  await expect(selector.getByRole("button", { name: "Quitar selección" })).toHaveCount(0);
  const search = selector.getByRole("combobox", { name: "Finca guardada" });
  await search.fill("Alta");
  await expect(selector).toHaveAttribute("data-selected-value", "farm-one");
  await expect(page.locator(".zone-map")).toHaveAttribute("data-pin-lat", "1.912345");
  await expect(page.getByRole("option", { name: /La Esperanza Alta.*Bogotá/ })).toBeVisible();
  await page.getByRole("option", { name: /La Esperanza Alta.*Bogotá/ }).click();
  await expect(selector).toHaveAttribute("data-selected-value", "farm-two");
  await expect(selector).toContainText("La Esperanza Alta");
  await expect(page.locator(".zone-map")).toHaveAttribute("data-pin-lat", "4.631");
});
