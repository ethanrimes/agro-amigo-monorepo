import { test, expect } from "@playwright/test";
const money = (n: number) =>
  new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    maximumFractionDigits: 0,
  }).format(n);
test("farms have independent locations, crop areas and saved financial plans", async ({
  page,
  context,
  browserName,
}) => {
  test.setTimeout(120000);
  page.setDefaultTimeout(12000);
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({
    latitude: 1.8547,
    longitude: -76.0505,
    accuracy: 12,
  });
  await page.goto("/farm");
  await page
    .getByRole("button", { name: "Usar mi ubicación GPS", exact: true })
    .click();
  await expect(page.locator(".location-coordinate")).toContainText("1.85470");
  await page.getByLabel("Departamento", { exact: true }).selectOption("HUILA");
  await page.getByLabel("Municipio", { exact: true }).selectOption("41551");
  await page.getByLabel("Nombre de tu finca").fill("La Esperanza");
  await page.getByLabel("Área total de la finca (hectáreas)").fill("3");
  await page.getByLabel("Cultivo principal").selectOption("2030300");
  await page
    .getByRole("button", { name: "Guardar mi finca →", exact: true })
    .click();
  await expect(page).toHaveURL(/\/farm\/[a-f0-9-]+$/);
  const farmA = page.url();
  await expect(page.locator(".farm-location-map")).toHaveAttribute(
    "data-latitude",
    "1.8547",
  );
  await expect(page.locator(".maplibregl-marker")).toBeVisible();
  await page.getByRole("tab", { name: "Mis cultivos", exact: true }).click();
  await page
    .getByRole("button", { name: "Editar cultivo", exact: true })
    .click();
  await page.getByLabel("Hectáreas de este cultivo").fill("2");
  await page.getByLabel("Rendimiento esperado (kg/ha)").fill("1000");
  await page
    .getByRole("button", { name: "Guardar cultivo", exact: true })
    .click();
  await expect(page.locator("dialog")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Agregar cultivo", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Cultivo o sistema" })
    .fill("Frijol");
  await page.getByRole("listbox").getByRole("option").first().click();
  await page.getByLabel("Hectáreas de este cultivo").fill("2");
  await page
    .getByRole("button", { name: "Guardar cultivo", exact: true })
    .click();
  await expect(page.locator("dialog [role=alert]")).toContainText(
    "supera el área",
  );
  await page.getByLabel("Hectáreas de este cultivo").fill("1");
  await page
    .getByRole("button", { name: "Guardar cultivo", exact: true })
    .click();
  await expect(page.locator(".managed-crop-card")).toHaveCount(2);
  await page
    .locator(".managed-crop-card")
    .first()
    .getByRole("link", { name: "Hacer presupuesto →" })
    .click();
  await expect(
    page.getByLabel("Área (hectáreas)", { exact: true }),
  ).toHaveValue("2");
  await page
    .getByRole("button", { name: "Ingresar mi precio", exact: true })
    .click();
  await page.getByLabel("Precio que recibirías por kg (COP)").fill("20000");
  for (let i = 0; i < 4; i++)
    await page
      .locator(".budget-costs input[type=number]")
      .nth(i)
      .fill("1000000");
  await page
    .getByLabel("Comisión sobre la venta (%)", { exact: true })
    .fill("5");
  await page
    .getByRole("button", {
      name: "Aplicar presupuesto a este cultivo",
      exact: true,
    })
    .click();
  await expect(page.locator(".save-status")).toContainText(
    "Presupuesto aplicado",
  );
  await page.goto(farmA);
  await expect(page.locator("[data-kpi=revenue]")).toHaveText(money(40000000));
  await expect(page.locator("[data-kpi=cost]")).toHaveText(money(10000000));
  await expect(page.locator("[data-kpi=profit]")).toHaveText(money(30000000));
  await expect(page.locator(".finance-pending")).toContainText("Frijol");
  await page.locator(".finance-table tbody a").click();
  await expect(
    page.getByLabel("Precio que recibirías por kg (COP)"),
  ).toHaveValue("20000");
  await expect(
    page.locator(".budget-costs input[type=number]").first(),
  ).toHaveValue("1000000");
  await page.goto("/farm");
  await page
    .getByRole("button", { name: "Agregar finca", exact: true })
    .click();
  await page
    .locator("dialog")
    .getByLabel("Departamento", { exact: true })
    .selectOption("HUILA");
  await page
    .locator("dialog")
    .getByLabel("Municipio", { exact: true })
    .selectOption("41551");
  await page.getByLabel("Nombre de tu finca").fill("El Recuerdo");
  await page
    .getByRole("button", { name: "Guardar mi finca →", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "El Recuerdo", exact: true }),
  ).toBeVisible();
  await expect(page.locator("[data-kpi=revenue]")).toHaveCount(0);
  await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
  await page.goto(farmA);
  await page.reload();
  await expect(page.locator("[data-kpi=profit]")).toHaveText(money(30000000));
  await expect(page.locator(".farm-location-map")).toHaveAttribute(
    "data-longitude",
    "-76.0505",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Descargar mis datos" }).click();
  expect((await download).suggestedFilename()).toMatch(/^finca-agroamigo-/);
  await page.locator(".farm-financials").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../../artifacts/restructure/farm-financial-" + browserName + ".png",
  });
  await page.screenshot({
    path: "../../artifacts/restructure/farm-full-" + browserName + ".png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("denied GPS gives a map/manual alternative and never inserts a false farm pin", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "geolocation", {
      value: {
        getCurrentPosition: (
          _: unknown,
          error: (e: { code: number }) => void,
        ) => error({ code: 1 }),
      },
      configurable: true,
    });
  });
  await page.goto("/farm");
  await page.getByRole("button", { name: "Usar mi ubicación GPS" }).click();
  await expect(
    page.getByText("El permiso de ubicación está desactivado.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.locator(".location-coordinate")).toHaveCount(0);
});
