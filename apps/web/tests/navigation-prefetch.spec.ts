import { expect, test, type Page } from '@playwright/test';

function rscPaths(page: Page) {
  const paths: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.searchParams.has('_rsc')) paths.push(url.pathname);
  });
  return paths;
}

test('mobile home waits for a tap before fetching shell destinations', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const paths = rscPaths(page);
  await page.goto('/');
  await expect(page.locator('.mobile-nav')).toBeVisible();
  await expect(page.locator('.product-card').first()).toBeVisible();
  await page.waitForTimeout(3000);
  expect(paths).toEqual([]);

  await page.locator('.topbar-actions a[aria-label="Reportar un problema"]').click();
  await expect(page).toHaveURL(/\/reportar\?from=/);
  await expect(page.getByRole('heading', { name: 'Reportar un problema' })).toBeVisible();
  await page.locator('.mobile-nav a[href="/products"]').click();
  await expect(page).toHaveURL(/\/products$/);
  await expect(page.getByRole('heading', { name: 'Productos agrícolas' })).toBeVisible();
  expect(paths).toContain('/reportar');
  expect(paths).toContain('/products');
});

test('desktop sidebar keeps destination prefetch', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const paths = rscPaths(page);
  await page.goto('/');
  await expect(page.locator('.sidebar')).toBeVisible();
  await expect.poll(() => ['products', 'markets', 'insumos', 'farm', 'saved', 'sources', 'reportar']
    .every(path => paths.includes('/' + path))).toBe(true);
});
