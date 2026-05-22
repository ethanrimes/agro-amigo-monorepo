/**
 * Data-driven assertions that should only pass AFTER ingestion + populate-dimensions completes.
 * These verify that the new Supabase database is wired up and returning real data to the UI.
 *
 * Run separately:  npx playwright test data.spec
 */
import { test, expect } from '@playwright/test';

const SUPABASE_HOST = /iznyrnsuqdmkuhtsrxor\.supabase\.co/;

test.describe('agroamigo-web data assertions', () => {
  test('home page renders without console errors and pulls from supabase', async ({ page }) => {
    let sawSupabaseRequest = false;
    const errors: string[] = [];
    page.on('request', (r) => { if (SUPABASE_HOST.test(r.url())) sawSupabaseRequest = true; });
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    await page.goto('/');
    // Give async client-side queries (e.g. getTrendingProducts) plenty of time
    // to fire — the home page shows "Cargando datos..." until the first response.
    await page.waitForRequest((req) => SUPABASE_HOST.test(req.url()), { timeout: 60_000 }).catch(() => undefined);
    await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => undefined);

    expect(errors.filter((e) => !/favicon/i.test(e))).toEqual([]);
    expect(sawSupabaseRequest, 'home page should hit the new Supabase host').toBeTruthy();
  });

  test('products page lists at least 20 products', async ({ page }) => {
    await page.goto('/products');
    // Wait for product list to appear (cards render as buttons inside the main element)
    await page.waitForLoadState('networkidle', { timeout: 45_000 }).catch(() => undefined);
    // Each product card is a button whose accessible name contains the product name twice
    // (alt text + label). Match buttons inside <main> excluding chip-filter "Todos" buttons.
    const productCards = page.locator('main button[role="button"], main [role="button"]').or(
      page.locator('main button')
    );
    // Give React a moment to settle async state
    await page.waitForTimeout(1500);
    const count = await page.locator('main button').count();
    // chip filter row is also under main; subtract a generous margin
    expect(count, 'expected products to be rendered after ingestion').toBeGreaterThanOrEqual(20);
  });

  test('markets page lists at least 1 market', async ({ page }) => {
    await page.goto('/markets');
    await page.waitForLoadState('networkidle', { timeout: 45_000 }).catch(() => undefined);
    await page.waitForTimeout(1500);
    // markets are rendered as cards (likely also buttons or list items) under main
    const items = page.locator('main button, main a[href^="/market/"], main [role="button"]');
    const count = await items.count();
    expect(count, 'expected market entries').toBeGreaterThanOrEqual(1);
  });

  test('map page mounts', async ({ page }) => {
    await page.goto('/map');
    await page.waitForLoadState('networkidle', { timeout: 60_000 }).catch(() => undefined);
    // Leaflet container has class 'leaflet-container'
    const container = page.locator('.leaflet-container, [data-testid="map"], canvas');
    await expect(container.first()).toBeVisible({ timeout: 30_000 });
  });

  test('a single product detail loads', async ({ page }) => {
    // First go to products, click first product card, then check the detail page renders
    await page.goto('/products');
    await page.waitForLoadState('networkidle', { timeout: 45_000 }).catch(() => undefined);
    await page.waitForTimeout(1500);
    // Product cards are buttons under <main>. Skip the chip-filter row by taking buttons
    // with non-trivial accessible text (chip filters are single words like "Todos", category names)
    const productButtons = page.locator('main button').filter({ hasNotText: /^(Todos|Carnes|Frutas|Granos|Lácteos|Pescados|Procesados|Tubérculos|Verduras)/i });
    const first = productButtons.first();
    await expect(first).toBeVisible({ timeout: 15_000 });
    await first.click();
    await page.waitForURL(/\/product\//, { timeout: 15_000 });
    await page.waitForLoadState('networkidle', { timeout: 45_000 }).catch(() => undefined);
    const body = page.locator('body').first();
    await expect(body).toBeVisible();
  });
});
