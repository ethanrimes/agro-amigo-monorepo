import { expect, test } from "@playwright/test";

test("mobile catalog search stays put while map eligibility loads", async ({ page, isMobile }) => {
  test.skip(!isMobile, "The native wrapper uses the mobile web layout");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/catalog", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await pending;
    await route.fulfill({ json: {
      products: [], regions: [], latestDate: null,
      filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
      categories: [], currencies: ["COP"], total: 0,
      pagination: { offset: 0, limit: 24, has_more: false },
      map_product: { id: "aguacate-hass", series: "city", presentation: "Kilogramo", units: "kg" },
    } });
  });
  await page.goto("/products");
  const search = page.getByRole("combobox", { name: "Buscar producto" });
  const map = page.getByRole("button", { name: "Ver mapa" });
  await expect(search).toBeVisible();
  await expect(map).toBeDisabled();
  const before = await search.boundingBox();
  expect(before).not.toBeNull();

  release();
  await expect(map).toBeEnabled();
  await expect.poll(async () => (await search.boundingBox())?.y).toBe(before!.y);
  const after = await search.boundingBox();
  expect(Math.abs(after!.y - before!.y)).toBeLessThanOrEqual(1);
  await search.click();
  await expect(search).toBeFocused();
  await expect(page).toHaveURL(/\/products/);
});

test("mobile catalog search stays put when loading finds no map product", async ({ page, isMobile }) => {
  test.skip(!isMobile, "The native wrapper uses the mobile web layout");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/catalog", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await pending;
    await route.fulfill({ json: {
      products: [], regions: [], latestDate: null,
      filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
      categories: [], currencies: ["COP"], total: 0,
      pagination: { offset: 0, limit: 24, has_more: false }, map_product: null,
    } });
  });
  await page.goto("/products");
  const search = page.getByRole("combobox", { name: "Buscar producto" });
  const map = page.getByRole("button", { name: "Ver mapa" });
  await expect(search).toBeVisible();
  await expect(map).toBeDisabled();
  const before = await search.boundingBox();
  expect(before).not.toBeNull();
  release();
  await expect(map).toHaveCount(0);
  await expect.poll(async () => (await search.boundingBox())?.y).toBe(before!.y);
  await search.click();
  await expect(search).toBeFocused();
  await expect(page).toHaveURL(/\/products/);
});

test("mobile catalog query does not move search when map eligibility changes", async ({ page, isMobile }) => {
  test.skip(!isMobile, "The native wrapper uses the mobile web layout");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/catalog", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const query = JSON.parse(route.request().postData() || "{}").q;
    if (query === "Calamar") await pending;
    await route.fulfill({ json: {
      products: [], regions: [], latestDate: null,
      filters: { region: "", reference_scope: "all", excluded_nonregional_count: 0, excluded_nonregional_reason: null },
      categories: [], currencies: ["COP"], total: 0,
      pagination: { offset: 0, limit: 24, has_more: false },
      map_product: query === "Calamar" ? null : { id: "aguacate-hass", series: "city", presentation: "Kilogramo", units: "kg" },
    } });
  });
  await page.goto("/products");
  const search = page.getByRole("combobox", { name: "Buscar producto" });
  const map = page.getByRole("button", { name: "Ver mapa" });
  await expect(map).toBeEnabled();
  const before = await search.boundingBox();
  expect(before).not.toBeNull();
  await search.fill("Calamar");
  await expect(map).toBeDisabled();
  release();
  await expect(map).toHaveCount(0);
  await expect.poll(async () => (await search.boundingBox())?.y).toBe(before!.y);
  await expect(search).toBeFocused();
  await expect(page).toHaveURL(/\/products\?q=Calamar/);
});
