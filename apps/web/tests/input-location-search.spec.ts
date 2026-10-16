import { expect, test } from "@playwright/test";

for (const count of [4, 12]) {
  test(`input comparison and coverage keep ${count} locations accessible without an unbounded list`, async ({ page }) => {
    const regions = Array.from({ length: count }, (_, index) => ({
      id: "fixture-input", name: "Ethrel 48 SL", category: "Reguladores", presentation: "200 centímetros cúbicos",
      department: "Valle del Cauca", municipality: index === count - 1 ? "Último municipio" : `Municipio ${index + 1}`,
      price: 90_000 - index * 1_000, observed_on: "2026-08-31",
      document_id: String(index + 1).padStart(64, "0"), source_locator: `PDF page ${index + 1},row 12`,
    }));
    await page.route("**/api/explore/input-aliases?**", (route) => route.fulfill({ json: [] }));
    await page.route("**/api/explore/input?**", (route) => {
      const url = new URL(route.request().url());
      const input = regions.find((item) => item.municipality === url.searchParams.get("municipality")) || regions[0];
      return route.fulfill({ json: { input, regions, history: [{ date: input.observed_on, price: input.price }] } });
    });
    await page.goto("/insumo/fixture-input?scope=municipality&department=Valle+del+Cauca&municipality=Municipio+1&history=all");
    const comparison = page.locator("section").filter({ has: page.getByRole("heading", { name: "Compara la misma presentación", exact: true }) });
    await expect(comparison.getByRole("article")).toHaveCount(Math.min(count, 6));
    if (count > 6) {
      const choice = comparison.getByRole("group", { name: "Comparar ubicación de este insumo", exact: true });
      const search = choice.getByRole("combobox");
      await search.click();
      await expect(choice.getByRole("option")).toHaveCount(8);
      await search.fill("ultimo municipio");
      await expect(choice).toHaveAttribute("data-selected-value", JSON.stringify(["Valle del Cauca", "Municipio 1"]));
      await expect(comparison.getByRole("article")).toHaveCount(6);
      await choice.getByRole("option", { name: /Último municipio/ }).click();
      await expect(choice).toHaveAttribute("data-selected-value", JSON.stringify(["Valle del Cauca", "Último municipio"]));
      await expect(comparison.getByRole("article")).toHaveCount(7);
      const chosen = comparison.getByRole("article").filter({ hasText: "Último municipio" });
      await expect(chosen).toContainText("79.000");
      await expect(chosen.getByRole("link", { name: "Ver fuente", exact: true })).toHaveAttribute("href", /page=12/);
      await expect(page).toHaveURL(/municipality=%C3%9Altimo\+municipio.*history=all/);
      await search.fill("no-such-location-zzzz");
      await expect(comparison.getByRole("article")).toHaveCount(7);
      await expect(choice.getByRole("button", { name: "Quitar selección", exact: true })).toHaveCount(0);
      await search.press("Escape");
    } else {
      await expect(comparison.getByRole("combobox")).toHaveCount(0);
    }
    await page.getByRole("tab", { name: "Abastecimiento", exact: true }).click();
    await expect(page.locator(".coverage-tags span")).toHaveCount(count > 6 ? 1 : count);
    if (count > 6) {
      const coverage = page.getByRole("group", { name: "Consultar ubicación con referencias", exact: true });
      await coverage.getByRole("combobox").fill("municipio 2");
      await coverage.getByRole("option", { name: /Municipio 2,/ }).click();
      await expect(page.locator(".coverage-tags span")).toHaveText("Municipio 2, Valle del Cauca");
      await expect(page).toHaveURL(/municipality=Municipio\+2.*history=all/);
      await expect(page.getByRole("heading", { name: "No hay datos de existencias de este insumo", exact: true })).toBeVisible();
    }
  });
}

test('input detail labels national comparison and each location’s report date without changing the chosen place', async ({ page }) => {
  const recentDate = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10);
  const entry = (department: string, municipality: string, price: number, observed_on: string, source: string) => ({
    id: 'fixture-input', name: 'Ethrel 48 SL', category: 'Reguladores', presentation: '200 centímetros cúbicos',
    department, municipality, price, observed_on, document_id: source.repeat(64), source_locator: 'PDF page 1,row 12',
  });
  const chosen = entry('Quindío', 'Armenia', 13_000, recentDate, 'a');
  const recentOther = entry('Huila', 'Neiva', 20_000, recentDate, 'b');
  const olderOther = entry('Cundinamarca', 'Bogotá', 40_000, '2019-04-12', 'c');
  await page.route('**/api/explore/input-aliases?**', route => route.fulfill({ json: [] }));
  await page.route('**/api/explore/input?**', route => {
    const all = new URL(route.request().url()).searchParams.get('history') === 'all';
    return route.fulfill({ json: {
      input: chosen, regions: all ? [chosen, recentOther, olderOther] : [chosen, recentOther],
      history: [{ date: chosen.observed_on, price: chosen.price }],
    } });
  });
  await page.goto('/insumo/fixture-input?scope=municipality&department=Quind%C3%ADo&municipality=Armenia&history=all');
  const comparison = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Compara la misma presentación', exact: true }) });
  await expect(comparison.getByLabel('Alcance de la comparación')).toContainText('Comparación nacional');
  await expect(comparison.getByLabel('Alcance de la comparación')).toContainText('Colombia');
  await expect(comparison.getByLabel('Alcance de la comparación')).toContainText('Todo el historial');
  await expect(comparison.getByLabel('Alcance de la comparación')).toContainText('200 centímetros cúbicos');
  await expect(comparison).toContainText('La ubicación elegida (Armenia, Quindío) determina el precio y el historial de arriba.');
  await expect(comparison.getByRole('article')).toHaveCount(3);
  const older = comparison.getByRole('article').filter({ hasText: 'Bogotá, Cundinamarca' });
  await expect(older).toContainText('Reporte:');
  await expect(older).toContainText('2019');
  await expect(page.locator('.input-detail-summary')).toContainText('13.000');
  await page.getByRole('combobox', { name: 'Historial de precios', exact: true }).selectOption('recent');
  await expect(comparison.getByLabel('Alcance de la comparación')).toContainText('Últimos 12 meses');
  await expect(comparison.getByRole('article')).toHaveCount(2);
  await expect(comparison.getByRole('article').filter({ hasText: 'Bogotá, Cundinamarca' })).toHaveCount(0);
  await expect(page.locator('.input-detail-summary')).toContainText('13.000');
  await expect(page).toHaveURL(/department=Quind%C3%ADo.*municipality=Armenia.*history=recent/);
});
