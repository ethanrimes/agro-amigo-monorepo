// Retained DANE originals exercise actual PDF.js pixels and render identity.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const originals = [
  { id: "32c73fee19652051a882222b51178105fd36e65098c9004992bfb971ead116fc", file: "pdf-viewer-render-a.pdf" },
  { id: "301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66", file: "pdf-viewer-render-b.pdf" },
] as const;

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

async function afterClickCommit(page: Page, label: string) {
  return page.evaluate(async (name) => {
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent?.trim() === name);
    if (!button) throw new Error(`Missing button: ${name}`);
    button.click();
    await Promise.resolve(); // React commit boundary; no rendering or network sleep.
    const canvas = document.querySelector<HTMLCanvasElement>(".pdf-paper canvas")!;
    return {
      label: canvas.getAttribute("aria-label"),
      rendered: canvas.getAttribute("data-rendered"),
      visibility: getComputedStyle(canvas).visibility,
      status: document.querySelector(".pdf-status")?.textContent?.trim() || "",
    };
  }, label);
}

test("PDF page identity withholds stale pixels through navigation and zoom", async ({ page }) => {
  await serveOriginals(page);
  await page.goto(`/evidence/${originals[0].id}?page=1`);
  const canvas = page.locator(".pdf-paper canvas");
  await expect(canvas).toHaveAttribute("data-rendered", "true");
  await expect(canvas).toHaveCSS("visibility", "visible");
  const first = await canvas.screenshot();

  expect(await afterClickCommit(page, "Siguiente →")).toMatchObject({
    label: "Página 2 del PDF", rendered: "false", visibility: "hidden",
    status: expect.stringContaining("Cargando página 2"),
  });
  await expect(canvas).toHaveAttribute("data-rendered", "true");
  await expect(canvas).toHaveCSS("visibility", "visible");
  const second = await canvas.screenshot();
  expect(second.equals(first)).toBe(false);

  expect(await afterClickCommit(page, "← Anterior")).toMatchObject({
    label: "Página 1 del PDF", rendered: "false", visibility: "hidden",
  });
  expect(await afterClickCommit(page, "Siguiente →")).toMatchObject({
    label: "Página 2 del PDF", rendered: "false", visibility: "hidden",
  });
  await expect(canvas).toHaveAttribute("data-rendered", "true");
  expect((await canvas.screenshot()).equals(second)).toBe(true);

  const zoom = await page.evaluate(async () => {
    const picker = document.querySelector<HTMLSelectElement>('select[aria-label="Tamaño del documento"]')!;
    picker.value = "1.5";
    picker.dispatchEvent(new Event("change", { bubbles: true }));
    await Promise.resolve();
    const canvas = document.querySelector<HTMLCanvasElement>(".pdf-paper canvas")!;
    return { rendered: canvas.dataset.rendered, visibility: getComputedStyle(canvas).visibility };
  });
  expect(zoom).toEqual({ rendered: "false", visibility: "hidden" });
  await expect(canvas).toHaveAttribute("data-rendered", "true");
  await expect(canvas).toHaveCSS("visibility", "visible");
  await expect(page.getByRole("link", { name: "Descargar archivo" }))
    .toHaveAttribute("href", `/api/evidence/${originals[0].id}/content`);

  // A second original exercises fresh document content and selected-page status.
  await page.goto(`/evidence/${originals[1].id}?page=1`);
  await expect(canvas).toHaveAttribute("aria-label", "Página 1 del PDF");
  await expect(canvas).toHaveAttribute("data-rendered", "true");
  await expect(canvas).toHaveCSS("visibility", "visible");
  expect((await canvas.screenshot()).equals(first)).toBe(false);
});
