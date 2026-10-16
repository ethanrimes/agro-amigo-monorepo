import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const originals = [
  { id: "6e7e5c976a1c49579f36df98ce72d1df29b6b6c22cbac1c656abc7fd08afa89a",
    file: "6e7e5c976a1c49579f36df98ce72d1df29b6b6c22cbac1c656abc7fd08afa89a.pdf" },
  { id: "301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66", file: "pdf-viewer-render-b.pdf" },
] as const;
const androidUserAgent = "Mozilla/5.0 (Linux; Android 17; wv) AppleWebKit/537.36 " +
  "Version/4.0 Chrome/152.0.7977.87 Mobile Safari/537.36 AgroAmigoAndroid/1.0";

async function serveOriginals(page: Page) {
  for (const source of originals) {
    const bytes = readFileSync(resolve(__dirname, "fixtures", source.file));
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(source.id);
    await page.route(`**/api/evidence/${source.id}/content`, (route) => route.fulfill({
      status: 200, contentType: "application/pdf", body: bytes,
    }));
    await page.route(`**/api/evidence/${source.id}?*`, (route) => route.fulfill({ json: {
      id: source.id, title: "PDF de prueba de dos páginas", kind: "original",
      media_type: "application/pdf", publisher: "DANE", reference_period: "Prueba",
      source_url: "https://www.dane.gov.co/", metadata: {}, records: [], parents: [], bytes: bytes.length,
    } }));
  }
}

async function snapshot(page: Page) {
  return page.locator(".pdf-paper canvas").evaluate((canvas: HTMLCanvasElement) => ({
    width: canvas.width, height: canvas.height,
    cssWidth: parseFloat(canvas.style.width), cssHeight: parseFloat(canvas.style.height),
    rendered: canvas.dataset.rendered, label: canvas.getAttribute("aria-label"),
  }));
}

test("Android wrapper keeps PDF zoom/page identity while bounding the backing bitmap", async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: test.info().project.use.baseURL,
    viewport: { width: 412, height: 845 }, deviceScaleFactor: 2.625,
    userAgent: androidUserAgent,
  });
  const page = await context.newPage();
  try {
    await serveOriginals(page);
    await page.goto(`/evidence/${originals[0].id}?page=1`);
    const canvas = page.locator(".pdf-paper canvas");
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    const fit = await snapshot(page);
    expect(fit.label).toBe("Página 1 del PDF");
    expect(fit.width * fit.height).toBeLessThanOrEqual(800_000);

    for (const [value, factor] of [["1.5", 1.5], ["2", 2]] as const) {
      await page.locator('select[aria-label="Tamaño del documento"]').selectOption(value);
      await expect.poll(async () => (await snapshot(page)).cssWidth)
        .toBeGreaterThan(fit.cssWidth * factor - 1);
      await expect(canvas).toHaveAttribute("data-rendered", "true");
      await expect(canvas).toHaveCSS("visibility", "visible");
      const zoomed = await snapshot(page);
      expect(zoomed.width * zoomed.height).toBeLessThanOrEqual(800_000);
      expect(zoomed.cssWidth).toBeCloseTo(fit.cssWidth * factor, 0);
      expect(zoomed.cssHeight).toBeCloseTo(fit.cssHeight * factor, 0);
      expect(zoomed.label).toBe("Página 1 del PDF");
    }

    await page.getByRole("button", { name: "Siguiente →" }).click();
    await expect(canvas).toHaveAttribute("aria-label", "Página 2 del PDF");
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    const nextPage = await snapshot(page);
    expect(nextPage.width * nextPage.height).toBeLessThanOrEqual(800_000);
    await page.getByRole("button", { name: "Siguiente →" }).click();
    await expect(canvas).toHaveAttribute("aria-label", "Página 3 del PDF");
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    expect((await snapshot(page)).width * (await snapshot(page)).height).toBeLessThanOrEqual(800_000);
    await page.getByRole("button", { name: "← Anterior" }).click();
    await expect(canvas).toHaveAttribute("aria-label", "Página 2 del PDF");
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    await page.getByRole("button", { name: "← Anterior" }).click();
    await expect(canvas).toHaveAttribute("aria-label", "Página 1 del PDF");
    await expect(canvas).toHaveAttribute("data-rendered", "true");

    await page.locator('select[aria-label="Tamaño del documento"]').selectOption("1");
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    expect((await snapshot(page)).cssWidth).toBeCloseTo(fit.cssWidth, 0);
    await expect(page.getByRole("link", { name: "Descargar archivo" }))
      .toHaveAttribute("href", `/api/evidence/${originals[0].id}/content`);

    await page.goto(`/evidence/${originals[1].id}?page=1`);
    await expect(canvas).toHaveAttribute("data-rendered", "true");
    await expect(canvas).toHaveAttribute("aria-label", "Página 1 del PDF");
    await expect(page.getByRole("link", { name: "Descargar archivo" }))
      .toHaveAttribute("href", `/api/evidence/${originals[1].id}/content`);
  } finally {
    await context.close();
  }
});
