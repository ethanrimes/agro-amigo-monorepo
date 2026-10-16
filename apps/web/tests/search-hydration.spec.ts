import { expect, test } from "@playwright/test";

const query = "MEDELLI\u0301N 2026-09-07";
const archivedDocument = {
  id: "a".repeat(64), title: "DANE - Medellín, Plaza Minorista .pdf",
  publisher: "DANE", reference_period: "Serie histórica completa",
  kind: "original", media_type: "application/pdf",
  observed_first: "2026-09-07", observed_last: "2026-09-07",
  retrieved_at: "2026-09-07T22:55:00.000000Z",
};

test("source search waits for event handlers before accepting text", async ({ page }) => {
  let releaseScripts!: () => void;
  const scriptsReady = new Promise<void>((resolve) => { releaseScripts = resolve; });
  let heldScripts = 0;
  const archiveQueries: string[] = [];
  await page.route(/\/_next\/static\/.*\.js(?:\?|$)/, async (route) => {
    heldScripts++;
    await scriptsReady;
    await route.continue();
  });
  await page.route("**/api/planning/library", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/source-archive?*", async (route) => {
    archiveQueries.push(new URL(route.request().url()).searchParams.get("q") || "");
    await route.fulfill({ json: { rows: [archivedDocument], hasMore: false, nextCursor: null } });
  });
  try {
    await page.goto("/sources", { waitUntil: "commit" });
    const search = page.locator(".source-library").getByRole("combobox", {
      name: "Buscar en los documentos", exact: true,
    });
    await expect(search).toBeVisible();
    await expect.poll(() => heldScripts).toBeGreaterThan(0);
    await expect(search).toBeDisabled();
    releaseScripts();
    await expect(search).toBeEnabled();
    await search.fill(query);
    await expect.poll(() => archiveQueries).toContain(query);
    await expect(search).toHaveValue(query);
    await expect(page.getByRole("option", { name: /Medellín, Plaza Minorista/ }))
      .toContainText("7 de septiembre de 2026");
  } finally {
    releaseScripts();
  }
});

test("finishing the initial document list preserves an active source query", async ({ page }) => {
  let releaseInitial!: () => void;
  const initialReady = new Promise<void>((resolve) => { releaseInitial = resolve; });
  let initialRequested = false;
  const archiveQueries: string[] = [];
  await page.route("**/api/planning/library", async (route) => {
    initialRequested = true;
    await initialReady;
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/source-archive?*", async (route) => {
    archiveQueries.push(new URL(route.request().url()).searchParams.get("q") || "");
    await route.fulfill({ json: { rows: [archivedDocument], hasMore: false, nextCursor: null } });
  });
  try {
    await page.goto("/sources", { waitUntil: "domcontentloaded" });
    const library = page.locator(".source-library");
    const search = library.getByRole("combobox", { name: "Buscar en los documentos", exact: true });
    await expect(search).toBeEnabled();
    await expect.poll(() => initialRequested).toBe(true);
    await search.fill(query);
    await expect.poll(() => archiveQueries).toContain(query);
    releaseInitial();
    await expect(library.locator(':scope > p[role="status"]')).toHaveText("1 documento");
    await expect(search).toHaveValue(query);
    await expect(page.getByRole("option", { name: /Medellín, Plaza Minorista/ }))
      .toContainText("7 de septiembre de 2026");
  } finally {
    releaseInitial();
  }
});

test("rapid catalog typing keeps the debounced URL and restores the query after browser back", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const firstQuery = "Leche cruda en finca";
  const longQuery = "Leche cruda en finca Cauca Nariño y Valle del Cauca";

  // This navigation control also verifies query retention while data is unavailable.
  // Keep every catalog request inside the browser fixture, including POST reads.
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503, json: { error: "El catálogo de prueba no está disponible." },
  }));
  await page.goto("/products", { waitUntil: "domcontentloaded" });
  const search = page.getByRole("combobox", {
    name: "Buscar producto",
    exact: true,
  });
  await expect(search).toBeEnabled();

  await search.pressSequentially(firstQuery, { delay: 75 });
  await page.waitForTimeout(300);
  await expect(search).toHaveValue(firstQuery);
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe(firstQuery);

  await search.fill("");
  await page.waitForTimeout(300);
  await expect.poll(() => new URL(page.url()).searchParams.has("q")).toBe(false);

  await search.pressSequentially(longQuery, { delay: 75 });
  await page.waitForTimeout(300);
  await expect(search).toHaveValue(longQuery);
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe(longQuery);
  expect(pageErrors).toEqual([]);

  await page.getByRole("link", { name: "Mercados", exact: true }).first().click();
  await expect(page).toHaveURL(/\/markets(?:\?|$)/);
  await page.goBack({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/products\?/);
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe(longQuery);
  await expect(search).toHaveValue(longQuery);
  expect(pageErrors).toEqual([]);
});


test("reference search waits for its URL filters and handlers before accepting text", async ({ page }) => {
  let releaseScripts!: () => void;
  const scriptsReady = new Promise<void>((resolve) => { releaseScripts = resolve; });
  let heldScripts = 0;
  const queries: string[] = [];
  await page.route(/\/_next\/static\/.*\.js(?:\?|$)/, async (route) => {
    heldScripts++;
    await scriptsReady;
    await route.continue();
  });
  await page.route("**/api/references?*", async (route) => {
    queries.push(new URL(route.request().url()).searchParams.get("q") || "");
    await route.fulfill({ json: { rows: [], total: 0, page: 0,
      options: { categories: [], publishers: [], currencies: [] } } });
  });
  try {
    await page.goto("/references?q=Leche%20cruda%20en%20finca", { waitUntil: "commit" });
    const search = page.getByRole("textbox", { name: "Buscar referencia", exact: true });
    await expect(search).toBeVisible();
    await expect.poll(() => heldScripts).toBeGreaterThan(0);
    await expect(search).toBeDisabled();
    releaseScripts();
    await expect(search).toBeEnabled();
    await expect(search).toHaveValue("Leche cruda en finca");
    await search.fill("LECHE cruda en finca Cauca Narino");
    await expect.poll(() => queries).toContain("LECHE cruda en finca Cauca Narino");
    await expect(search).toHaveValue("LECHE cruda en finca Cauca Narino");
  } finally {
    releaseScripts();
  }
});
