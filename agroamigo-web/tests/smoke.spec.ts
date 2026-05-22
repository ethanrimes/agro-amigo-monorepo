import { test, expect, Page } from '@playwright/test';

const ROUTES = [
  { path: '/', name: 'home' },
  { path: '/products', name: 'products' },
  { path: '/markets', name: 'markets' },
  { path: '/map', name: 'map' },
  { path: '/insumos', name: 'insumos' },
  { path: '/auth', name: 'auth' },
];

function attachConsoleAndNetworkListeners(page: Page) {
  const consoleErrors: string[] = [];
  const failedRequests: { url: string; status?: number; failure?: string }[] = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (
        /favicon/i.test(text) ||
        /Failed to load resource: the server responded with a status of 404/.test(text)
      ) {
        return;
      }
      consoleErrors.push(text);
    }
  });

  page.on('pageerror', (err) => {
    consoleErrors.push(`pageerror: ${err.message}`);
  });

  page.on('requestfailed', (req) => {
    failedRequests.push({ url: req.url(), failure: req.failure()?.errorText });
  });

  page.on('response', (resp) => {
    const status = resp.status();
    const url = resp.url();
    if (status >= 500) {
      failedRequests.push({ url, status });
    }
  });

  return { consoleErrors, failedRequests };
}

test.describe('agroamigo-web smoke', () => {
  for (const { path, name } of ROUTES) {
    test(`loads ${name} (${path})`, async ({ page }) => {
      const { consoleErrors, failedRequests } = attachConsoleAndNetworkListeners(page);

      const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
      expect(response, `no response for ${path}`).not.toBeNull();
      expect(response!.status(), `${path} returned non-OK`).toBeLessThan(400);

      await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => undefined);

      const body = page.locator('body').first();
      await expect(body).toBeVisible();

      const meaningfulFailures = failedRequests.filter(
        (f) => {
          if (!/iznyrnsuqdmkuhtsrxor\.supabase\.co/.test(f.url) && !/localhost:3000/.test(f.url)) {
            return false;
          }
          // Image storage 400/404/ORB failures are expected for products without
          // uploaded images — the ProductImage component swaps in a category fallback.
          if (/\/storage\/v1\/object\/public\/product-images\//.test(f.url)) {
            return false;
          }
          return true;
        }
      );

      if (consoleErrors.length || meaningfulFailures.length) {
        console.log(`[${name}] console errors:`, consoleErrors);
        console.log(`[${name}] failed requests:`, meaningfulFailures);
      }

      expect(consoleErrors, `console errors on ${path}`).toEqual([]);
      expect(meaningfulFailures, `failed network requests on ${path}`).toEqual([]);
    });
  }
});
