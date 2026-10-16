import { expect, test, type Page } from "@playwright/test";

async function chooseProduct(page: Page, name: string) {
  await page.getByRole("combobox", { name: "Buscar producto en el boletín", exact: true }).fill(name);
  await page.getByRole("option", { name, exact: true }).click();
}

const latest = "2026-09-29";
const older = "2019-04-24";
const row = (date: string) => [{
  observed_on: date,
  product_name: date === latest ? "Habichuela" : "Zanahoria",
  market_name: "Villavicencio, CAV",
  price: date === latest ? 2100 : 885,
  unit: "kg",
  change_percent: null,
  document_id: (date === latest ? "a" : "b").repeat(64),
  source_page: 1,
  source_locator: "Boletín diario!row 18,col 22",
}];

test("switching dates hides the previous price and evidence while the next request is pending", async ({ page }) => {
  let releaseOlder!: () => void;
  const olderPending = new Promise<void>((resolve) => { releaseOlder = resolve; });
  await page.route("**/api/planning/daily**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-supply-source")) {
      await route.fulfill({ json: null });
      return;
    }
    if (url.pathname.endsWith("daily-dates")) {
      await route.fulfill({ json: [{ date: latest }, { date: older }] });
      return;
    }
    const date = url.searchParams.get("date") || latest;
    if (date === older) await olderPending;
    await route.fulfill({ json: row(date) });
  });
  await page.goto("/daily");
  await chooseProduct(page, "Habichuela");
  await expect(page.locator(".input-card")).toContainText("Habichuela");
  await page.getByLabel("Fecha del boletín").fill(older);
  await expect(page.locator('[role="status"]').filter({ hasText: "Consultando el boletín…" })).toBeVisible();
  await expect(page.locator(".input-card")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Comprobar este precio" })).toHaveCount(0);
  releaseOlder();
  await chooseProduct(page, "Zanahoria");
  await expect(page.locator(".input-card")).toContainText("Zanahoria");
  await expect(page.locator(".input-card")).not.toContainText("Habichuela");
});

test("retry clears an error and refreshes the same date URL", async ({ page }) => {
  let olderAttempts = 0;
  let releaseRetry!: () => void;
  const retryPending = new Promise<void>((resolve) => { releaseRetry = resolve; });
  await page.route("**/api/planning/daily**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/daily-supply-source")) {
      await route.fulfill({ json: null });
      return;
    }
    if (url.pathname.endsWith("daily-dates")) {
      await route.fulfill({ json: [{ date: latest }, { date: older }] });
      return;
    }
    const date = url.searchParams.get("date") || latest;
    if (date === older && ++olderAttempts === 1) {
      await route.fulfill({ status: 503, json: { error: "Error de prueba" } });
      return;
    }
    if (date === older) await retryPending;
    await route.fulfill({ json: row(date) });
  });
  await page.goto("/daily");
  await chooseProduct(page, "Habichuela");
  await expect(page.locator(".input-card")).toContainText("Habichuela");
  await page.getByLabel("Fecha del boletín").fill(older);
  await expect(page.locator(".empty-state[role=alert]")).toContainText("Error de prueba");
  await page.getByRole("button", { name: "Volver a intentar" }).click();
  await expect(page.locator(".empty-state[role=alert]")).toHaveCount(0);
  await expect(page.locator('[role="status"]').filter({ hasText: "Consultando el boletín…" })).toBeVisible();
  releaseRetry();
  await chooseProduct(page, "Zanahoria");
  await expect(page.locator(".input-card")).toContainText("Zanahoria");
  await expect.poll(() => olderAttempts).toBe(2);
});
