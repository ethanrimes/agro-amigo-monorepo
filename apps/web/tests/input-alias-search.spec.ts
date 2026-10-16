import { test, expect } from "@playwright/test";

test("commercial-line search keeps coverage and history when opening an exact identity", async ({ page }) => {
  const choices = Array.from({ length: 12 }, (_, index) => ({
    id: `wire-line-${index}`,
    name: "Alambre de púas",
    presentation: "rollo por 200 metros",
    product_line: index === 11 ? "Iowa" : `Finquero ${index + 1}`,
    brand: "Proalco Bekaert",
    department: "Antioquia",
    municipality: "",
    price: index === 11 ? 147122.2222222 : 152970.5,
    observed_on: "2023-01-31",
  }));
  await page.route("**/api/explore/input?**", (route) => route.fulfill({ status: 404, json: { error: "No encontramos esta referencia." } }));
  await page.route("**/api/explore/input-aliases?**", (route) => route.fulfill({ json: choices }));
  await page.goto("/insumo/legacy-wire?department=Antioquia&scope=department&history=all");
  const selector = page.getByRole("group", { name: "Línea comercial del insumo", exact: true });
  const search = selector.getByRole("combobox");
  await search.fill("");
  await search.press("ArrowDown");
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(8);
  await search.fill("iowa");
  await expect(page).toHaveURL(/\/insumo\/legacy-wire/);
  const option = page.getByRole("listbox").getByRole("option");
  await expect(option).toHaveCount(1);
  await expect(option).toContainText("rollo por 200 metros");
  await expect(option).toContainText("Antioquia");
  await expect(option).toContainText("147.122");
  await option.click();
  await expect(page).toHaveURL(/\/insumo\/wire-line-11\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get("department")).toBe("Antioquia");
  expect(url.searchParams.get("scope")).toBe("department");
  expect(url.searchParams.get("history")).toBe("all");
});
