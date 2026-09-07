import { resolve } from 'node:path';
import { test, expect } from '@playwright/test';

for (const viewport of [
  { width: 375, height: 667 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 932, height: 430 },
]) {
  test(`phone layout fills ${viewport.width}x${viewport.height} with equal tabs`, async ({ page, isMobile }, info) => {
    test.skip(!isMobile, 'Phone layout regression');
    await page.setViewportSize(viewport);
    await page.goto('/saved');
    const nav = page.getByRole('navigation', { name: 'Navegación móvil' });
    await expect(nav).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Guarda lo que te interesa' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Guardados' })).toHaveAttribute('aria-current', 'page');
    const layout = await page.evaluate(() => {
      const box = (selector: string) => document.querySelector(selector)!.getBoundingClientRect().toJSON();
      return {
        width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
        nav: box('.mobile-nav'), shell: box('.main-shell'), content: box('.app-content'),
        tabs: [...document.querySelectorAll('.mobile-nav a')].map(a => a.getBoundingClientRect().toJSON()),
        font: getComputedStyle(document.body).fontFamily,
      };
    });
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width);
    expect(layout.shell.height).toBeGreaterThanOrEqual(layout.height);
    expect(layout.content.width).toBe(layout.width);
    expect(layout.nav.bottom).toBeCloseTo(layout.height, 0);
    expect(layout.nav.width).toBe(layout.width);
    for (const tab of layout.tabs) {
      expect(tab.width).toBeCloseTo(layout.width / 5, 0);
      expect(tab.height).toBeGreaterThanOrEqual(48);
    }
    expect(layout.font).not.toMatch(/Manrope|DM Sans|Georgia/);
    await page.screenshot({ path: resolve(__dirname, '../../../artifacts', `layout-${info.project.name}-${viewport.width}.png`) });
    await nav.getByRole('link', { name: 'Mi finca' }).click();
    await expect(page).toHaveURL(/\/farm$/);
    await expect(nav.getByRole('link', { name: 'Mi finca' })).toHaveAttribute('aria-current', 'page');
    await expect(nav.locator('[aria-current]')).toHaveCount(1);
    await page.goto('/plan');
    await expect(nav.getByRole('link', { name: 'Mi finca' })).toHaveAttribute('aria-current', 'location');
    await page.goto('/daily');
    await expect(nav.getByRole('link', { name: 'Precios' })).toHaveAttribute('aria-current', 'location');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('larger phone text keeps navigation and form controls usable', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'Phone text-size regression');
  await page.goto('/farm');
  await page.addStyleTag({ content: 'html { -webkit-text-size-adjust: 130%; }' });
  await page.locator('.farm-editor').getByRole('combobox', { name: 'Departamento', exact: true }).selectOption('HUILA');
  await page.getByRole('combobox', { name: 'Municipio', exact: true }).selectOption('41551');
  const field = page.getByLabel('Nombre de tu finca');
  await expect(field).toBeVisible();
  await field.fill('Mi finca');
  await expect(field).toHaveValue('Mi finca');
  expect(await field.evaluate(e => parseFloat(getComputedStyle(e).fontSize))).toBeGreaterThanOrEqual(16);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
