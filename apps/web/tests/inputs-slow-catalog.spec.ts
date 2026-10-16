import { expect, test } from "@playwright/test";

function input(name: string, municipality = "") {
  return {
    id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    name,
    category: "Fertilizantes",
    presentation: "Bulto de 50 kilogramos",
    price: 125_000,
    observed_on: "2026-08-31",
    department: "Huila",
    municipality,
    document_id: "a".repeat(64),
    source_locator: "PDF page 1,row 2",
    brand: "",
    registration: "",
    product_line: "",
  };
}

test("grouped inputs tolerate a 31-second response and ignore a late old-filter response", async ({ page }) => {
  test.setTimeout(110_000);
  await page.route("**/api/planning/municipalities", (route) =>
    route.fulfill({ json: [{ department: "Huila" }] }),
  );

  let firstDepartmentFinished = false;
  let staleMunicipalityFinished = false;
  let departmentRequests = 0;
  let municipalityRequests = 0;
  await page.route("**/api/planning/inputs?**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (query.get("grouped") !== "true") return route.fulfill({ json: [] });
    const scope = query.get("scope");
    if (scope === "department") {
      departmentRequests += 1;
      if (departmentRequests === 1) {
        await new Promise((resolve) => setTimeout(resolve, 31_000));
        firstDepartmentFinished = true;
        return route.fulfill({ json: [input("Promedio departamental tardío")] });
      }
      return route.fulfill({ json: [input("Promedio departamental vigente")] });
    }
    if (scope === "municipality") {
      municipalityRequests += 1;
      await new Promise((resolve) => setTimeout(resolve, 31_000));
      staleMunicipalityFinished = true;
      try {
        await route.fulfill({ json: [input("Municipio antiguo", "Armenia")] });
      } catch {
        // A filter change may abort the browser request before this late reply.
      }
      return;
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/insumos?department=Huila&history=all");
  await expect(page.locator(".input-catalog-card h2", { hasText: "Promedio departamental tardío" }))
    .toBeVisible({ timeout: 45_000 });
  expect(firstDepartmentFinished).toBe(true);

  const coverage = page.getByRole("combobox", { name: "Cobertura del precio" });
  await coverage.selectOption("municipality");
  await expect.poll(() => municipalityRequests).toBe(1);
  await coverage.selectOption("department");
  await expect(page.locator(".input-catalog-card h2", { hasText: "Promedio departamental vigente" }))
    .toBeVisible();
  await expect.poll(() => staleMunicipalityFinished, { timeout: 35_000 }).toBe(true);
  await expect(page.locator(".input-catalog-card h2", { hasText: "Promedio departamental vigente" }))
    .toBeVisible();
  await expect(page.locator(".input-catalog-card h2", { hasText: "Municipio antiguo" })).toHaveCount(0);
  await expect(page.getByLabel("Filtros aplicados")).toContainText("Promedio departamental");
});
