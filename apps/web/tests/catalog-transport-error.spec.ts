import { expect, test } from '@playwright/test';

const emptyCatalog = {
  products: [], regions: [], latestDate: null,
  filters: { region: '', reference_scope: 'all', excluded_nonregional_count: 0, excluded_nonregional_reason: null },
  categories: [], currencies: ['COP'], total: 0,
  pagination: { offset: 0, limit: 24, has_more: false }, map_product: null,
};

test('a failed catalog transport shows a useful Spanish error and explicit Retry', async ({ page }) => {
  let failed = false;
  await page.route('**/api/catalog', route => {
    if (route.request().method() !== 'POST') return route.continue();
    if (!failed) { failed = true; return route.abort('failed'); }
    return route.fulfill({ json: emptyCatalog });
  });
  await page.goto('/products');
  const alert = page.locator('.empty-state[role="alert"]');
  await expect(alert).toContainText('No pudimos conectar con el catálogo. Revisa tu conexión e intenta de nuevo.');
  await expect(alert).not.toContainText('Failed to fetch');
  await alert.getByRole('button', { name: 'Volver a intentar' }).click();
  await expect(alert).toHaveCount(0);
  expect(failed).toBe(true);
});

test('malformed catalog JSON is localized and Retry clears the error', async ({ page }) => {
  let malformed = false;
  await page.route('**/api/catalog', route => {
    if (route.request().method() !== 'POST') return route.continue();
    if (!malformed) {
      malformed = true;
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{' });
    }
    return route.fulfill({ json: emptyCatalog });
  });
  await page.goto('/products');
  const alert = page.locator('.empty-state[role="alert"]');
  await expect(alert).toContainText('No pudimos leer la respuesta del catálogo. Intenta de nuevo.');
  await expect(alert).not.toContainText('Unexpected token');
  await alert.getByRole('button', { name: 'Volver a intentar' }).click();
  await expect(alert).toHaveCount(0);
  expect(malformed).toBe(true);
});
