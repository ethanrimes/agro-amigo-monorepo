import { expect, test, type Page } from "@playwright/test";

async function chooseProduct(page: Page, name: string) {
  await page.getByRole("combobox", { name: "Buscar producto en el boletín", exact: true }).fill(name);
  await page.getByRole("option", { name, exact: true }).click();
}

test("a retained market remains visible when another date has no prices for it", async ({ page }) => {
  let releaseOlder!: () => void;
  const olderPending = new Promise<void>((resolve) => { releaseOlder = resolve; });
  await page.route("**/api/planning/daily**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-supply-source")) {
      await route.fulfill({ json: null });
      return;
    }
    if (url.pathname.endsWith("daily-dates")) {
      await route.fulfill({ json: [{ date: "2021-12-31" }, { date: "2021-12-30" }] });
      return;
    }
    const date = url.searchParams.get("date") || "2021-12-31";
    if (date === "2021-12-30") await olderPending;
    await route.fulfill({ json: [{
      observed_on: date, product_name: "Chócolo mazorca",
      market_name: date === "2021-12-31" ? "Barranquilla" : "Bogotá, Corabastos",
      price: 1230, unit: "kg", change_percent: 0, document_id: "a".repeat(64),
      source_page: null, source_locator: "Boletín diario!row 10,col 2",
    }] });
  });
  await page.goto("/daily");
  const market = page.getByRole("combobox", { name: "Plaza del boletín" });
  const choice = page.getByRole("group", { name: "Plaza del boletín", exact: true });
  await chooseProduct(page, "Chócolo mazorca");
  await expect(page.locator(".input-card")).toContainText("Barranquilla");
  await market.fill("Barranquilla");
  await page.getByRole("option", { name: "Barranquilla", exact: true }).click();
  await page.getByLabel("Fecha del boletín").fill("2021-12-30");
  await expect(page.locator(".input-card")).toHaveCount(0);
  await expect(choice).toHaveAttribute("data-selected-value", "Barranquilla");
  await expect(page.locator(".applied-filters")).toContainText("Barranquilla");
  releaseOlder();
  await expect(choice).toContainText("Barranquilla · sin datos en esta fecha");
  await expect(choice).toHaveAttribute("data-selected-value", "Barranquilla");
  await expect(page.locator(".field-help[role=status]")).toContainText("La plaza sigue seleccionada");
  await expect(page.locator(".input-card")).toHaveCount(0);
  await choice.getByRole("button", { name: "Quitar selección" }).click();
  await expect(market).toHaveValue("");
  await expect(page.locator(".input-card")).toContainText("Bogotá, Corabastos");
  await expect(page.locator(".applied-filters")).not.toContainText("Barranquilla");
  await expect(page.getByText(/La plaza sigue seleccionada/)).toHaveCount(0);
});

test("a date chosen while the bulletin opens is retained after client startup", async ({ page }) => {
  await page.route("**/_next/static/**/*.js", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.continue();
  });
  await page.route("**/api/planning/daily**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-supply-source")) {
      await route.fulfill({ json: null });
      return;
    }
    if (url.pathname.endsWith("/daily-dates")) {
      await route.fulfill({ json: [{ date: "2026-09-29" }, { date: "2019-04-24" }] });
      return;
    }
    const day = url.searchParams.get("date") || "2026-09-29";
    if (!url.searchParams.has("date")) await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ json: [{
      observed_on: day, product_name: day === "2019-04-24" ? "Zanahoria" : "Habichuela",
      market_name: "Villavicencio, CAV", price: day === "2019-04-24" ? 885 : 2100,
      unit: "kg", change_percent: null, document_id: "a".repeat(64),
      source_page: null, source_locator: "Boletín diario!row 18,col 22",
    }] });
  });
  await page.goto("/daily", { waitUntil: "commit" });
  await page.getByLabel("Fecha del boletín").fill("2019-04-24");
  await expect(page.getByLabel("Fecha del boletín")).toHaveValue("2019-04-24");
  await chooseProduct(page, "Zanahoria");
  await expect(page.locator(".input-card")).toContainText("Zanahoria");
  await expect(page.locator(".input-card")).toContainText("885");
  await expect(page.locator(".applied-filters")).toContainText("24 de abril de 2019");
});

test("daily date, product, and market filters round-trip through reload, back, and a shared URL", async ({ page, context }) => {
  const dates = [{ date: "2021-12-31" }, { date: "2021-12-30" }];
  await context.route("**/api/planning/daily**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-dates")) return route.fulfill({ json: dates });
    if (url.pathname.endsWith("/daily-supply-source")) return route.fulfill({ json: null });
    const date = url.searchParams.get("date") || "2021-12-31";
    return route.fulfill({ json: [
      { observed_on: date, product_name: "Zanahoria", market_name: "Pasto, El Potrerillo", price: 1230,
        unit: "kg", change_percent: 0, document_id: "a".repeat(64), source_page: 1, source_locator: "row 9" },
      { observed_on: date, product_name: "Zanahoria", market_name: "Ipiales, Centro de acopio", price: 1450,
        unit: "kg", change_percent: 1, document_id: "b".repeat(64), source_page: 1, source_locator: "row 10" },
    ] });
  });

  await page.goto("/daily?date=2021-12-31");
  await chooseProduct(page, "Zanahoria");
  await expect.poll(() => new URL(page.url()).searchParams.get("product")).toBe("Zanahoria");
  await expect.poll(() => new URL(page.url()).searchParams.get("date")).toBe("2021-12-31");

  const market = page.getByRole("group", { name: "Plaza del boletín", exact: true });
  await market.getByRole("combobox").fill("Pasto");
  await market.getByRole("option", { name: "Pasto, El Potrerillo", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("market")).toBe("Pasto, El Potrerillo");
  await expect(page.locator(".input-card")).toHaveCount(1);

  await page.reload();
  await expect(page.getByLabel("Fecha del boletín")).toHaveValue("2021-12-31");
  await expect(page.getByRole("group", { name: "Buscar producto en el boletín", exact: true }))
    .toHaveAttribute("data-selected-value", "Zanahoria");
  await expect(market).toHaveAttribute("data-selected-value", "Pasto, El Potrerillo");
  await expect(page.locator(".input-card")).toContainText("Pasto, El Potrerillo");

  await page.goBack();
  await expect.poll(() => new URL(page.url()).searchParams.get("market")).toBeNull();
  await expect(page.getByRole("group", { name: "Buscar producto en el boletín", exact: true }))
    .toHaveAttribute("data-selected-value", "Zanahoria");
  await expect(page.locator(".input-card")).toHaveCount(2);

  await page.goForward();
  await expect.poll(() => new URL(page.url()).searchParams.get("market")).toBe("Pasto, El Potrerillo");
  const shared = await context.newPage();
  await shared.goto(page.url());
  await expect(shared.getByLabel("Fecha del boletín")).toHaveValue("2021-12-31");
  await expect(shared.getByRole("group", { name: "Buscar producto en el boletín", exact: true }))
    .toHaveAttribute("data-selected-value", "Zanahoria");
  await expect(shared.getByRole("group", { name: "Plaza del boletín", exact: true }))
    .toHaveAttribute("data-selected-value", "Pasto, El Potrerillo");
  await expect(shared.locator(".input-card")).toContainText("Pasto, El Potrerillo");
});

test("daily bulletin exposes an older annex date and its exact workbook cell", async ({ page }) => {
  await page.setViewportSize({ width: 411, height: 845 });
  const documentId = "a".repeat(64);
  const requestedDates: string[] = [];
  await page.route("**/api/planning/daily**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-supply-source")) {
      await route.fulfill({ json: null });
      return;
    }
    if (url.pathname.endsWith("/daily-dates")) {
      await route.fulfill({ json: [{ date: "2026-09-28" }, { date: "2019-04-24" }] });
      return;
    }
    const date = url.searchParams.get("date") || "2026-09-28";
    requestedDates.push(date);
    await route.fulfill({ json: date === "2019-04-24" ? [{
      observed_on: date, product_name: "Zanahoria", market_name: "Villavicencio, CAV",
      price: 885, unit: "kg", change_percent: null, document_id: documentId,
      source_page: null, source_locator: "Boletín diario!row 18,col 22",
    }] : [{
      observed_on: date, product_name: "Habichuela", market_name: "Montería, Mercado del Sur",
      price: 2100, unit: "kg", change_percent: 1, document_id: "b".repeat(64),
      source_page: null, source_locator: "Boletín diario!row 20,col 6",
    }] });
  });

  await page.goto("/daily");
  await expect(page.getByLabel("Fecha del boletín")).toHaveValue("2026-09-28");
  await page.getByRole("button", { name: "Anterior" }).click();
  await expect(page.getByLabel("Fecha del boletín")).toHaveValue("2019-04-24");
  await expect(page.locator(".applied-filters")).toContainText("24 de abril de 2019");
  await chooseProduct(page, "Zanahoria");
  const card = page.locator(".input-card").filter({ hasText: "Zanahoria" });
  await expect(card).toContainText("Villavicencio, CAV");
  await expect(card).toContainText("885");
  const source = card.getByRole("link", { name: "Comprobar este precio" });
  await expect(source).toHaveAttribute("href", new RegExp(`/evidence/${documentId}\\?.*locator=`));
  expect(new URL((await source.getAttribute("href"))!, "https://example.test").searchParams.get("locator"))
    .toBe("Boletín diario!row 18,col 22");
  expect(requestedDates).toContain("2019-04-24");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
