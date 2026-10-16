import { test, expect, type Page } from '@playwright/test';

async function dailyFixture(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/planning/daily-dates', route => route.fulfill({ json: [{ date: '2012-06-27' }] }));
  await page.route('**/api/planning/daily', route => route.fulfill({ json: [{
    observed_on: '2012-06-27', product_name: 'Ahuyama', market_name: 'Bogotá',
    price: 775, unit: 'kg', change_percent: -1, document_id: 'daily-fixture',
    source_page: 1, source_locator: 'PDF page 1',
  }] }));
  await page.route('**/api/planning/daily-supply-source**', route => route.fulfill({ json: null }));
  await page.goto('/daily');
  await page.addStyleTag({ content: `
    .searchable-select[aria-label="Buscar producto en el boletín"] {
      position: fixed; bottom: 220px; left: 40px; width: 260px; z-index: 100; background: white;
    }
    .mobile-nav { height: 150px; }
  ` });
}

test('search suggestions avoid a visible fixed mobile navigation bar', async ({ page }) => {
  await dailyFixture(page);
  const search = page.getByRole('combobox', { name: 'Buscar producto en el boletín', exact: true });
  await search.fill('ahuyama');
  const popup = page.getByRole('listbox', { name: 'Sugerencias: Buscar producto en el boletín', exact: true });
  await expect(popup).toHaveAttribute('data-placement', 'above');
  const [field, list, nav] = await Promise.all([search.boundingBox(), popup.boundingBox(), page.locator('.mobile-nav').boundingBox()]);
  expect(field && list && nav).toBeTruthy();
  expect(list!.y + list!.height).toBeLessThan(field!.y);
  expect(list!.y + list!.height).toBeLessThan(nav!.y);
  await popup.getByRole('option', { name: 'Ahuyama', exact: true }).click();
  await expect(page.getByRole('article')).toContainText('775');
});

test('without a visible fixed nav the same field may use available space below', async ({ page }) => {
  await dailyFixture(page);
  await page.addStyleTag({ content: '.mobile-nav { display: none !important; }' });
  const search = page.getByRole('combobox', { name: 'Buscar producto en el boletín', exact: true });
  await search.fill('ahuyama');
  const popup = page.getByRole('listbox', { name: 'Sugerencias: Buscar producto en el boletín', exact: true });
  await expect(popup).toHaveAttribute('data-placement', 'below');
  const [field, list] = await Promise.all([search.boundingBox(), popup.boundingBox()]);
  expect(field && list).toBeTruthy();
  expect(list!.y).toBeGreaterThanOrEqual(field!.y + field!.height);
});

test('coarse-pointer option tap dismisses input focus after choosing a suggestion', async ({ browser }) => {
  const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  try {
    const page = await context.newPage();
    await dailyFixture(page);
    expect(await page.evaluate(() => window.matchMedia('(pointer: coarse)').matches)).toBe(true);
    const search = page.getByRole('combobox', { name: 'Buscar producto en el boletín', exact: true });
    await search.fill('ahu');
    await expect(search).toBeFocused();
    await page.getByRole('listbox', { name: 'Sugerencias: Buscar producto en el boletín' })
      .getByRole('option', { name: 'Ahuyama', exact: true }).tap();
    await expect(search).toHaveValue('');
    await expect(search).not.toBeFocused();
    await expect(page.getByRole('listbox', { name: 'Sugerencias: Buscar producto en el boletín' })).toHaveCount(0);
    await expect(page.getByRole('article')).toContainText('775');
  } finally {
    await context.close();
  }
});

test('desktop mouse and keyboard selection preserve combobox focus', async ({ browser }) => {
  const context = await browser.newContext({ hasTouch: false, isMobile: false, viewport: { width: 1440, height: 1000 } });
  try {
    const page = await context.newPage();
    await dailyFixture(page);
    expect(await page.evaluate(() => window.matchMedia('(pointer: coarse)').matches)).toBe(false);
    const search = page.getByRole('combobox', { name: 'Buscar producto en el boletín', exact: true });
    await search.fill('ahu');
    await page.getByRole('listbox', { name: 'Sugerencias: Buscar producto en el boletín' })
      .getByRole('option', { name: 'Ahuyama', exact: true }).click();
    await expect(search).toHaveValue('');
    await expect(search).toBeFocused();
    await expect(page.getByRole('article')).toContainText('775');
    await search.fill('ahu');
    await search.press('ArrowDown');
    await expect(search).toHaveAttribute('aria-activedescendant', /.+/);
    await search.press('Enter');
    await expect(search).toHaveValue('');
    await expect(search).toBeFocused();
  } finally {
    await context.close();
  }
});
