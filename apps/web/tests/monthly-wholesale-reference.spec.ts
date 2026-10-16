import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";

const sourceId = "f5d71069f7e57759ed675ff9a003c37854eca7f13e17d68f7f39845ae36b3d02";

test("monthly wholesale reference opens and retains exact DANE August 2026 cells", async ({ page, request }) => {
  const latest = await request.get("/api/data-references?kind=wholesale&page=0");
  expect(latest.status()).toBe(200);
  const options = await latest.json();
  expect(options.dates).toContain("2026-08-31");

  const pinned = await request.get(
    "/api/data-references?kind=wholesale&date=2026-08-31&q=Aceite%20vegetal%20mezcla&page=0",
  );
  expect(pinned.status()).toBe(200);
  const data = await pinned.json();
  const barranquilla = data.rows.find((row: any) => row.details.Ciudad === "Barranquilla");
  const bogota = data.rows.find((row: any) => row.details.Ciudad === "Bogotá");
  expect(barranquilla).toMatchObject({
    name: "Aceite vegetal mezcla**",
    document_id: sourceId,
    source_locator: expect.stringMatching(/^1!row\s*64,col\s*2(?:; monthly-annex-v[0-9]+)?$/),
    details: { "Precio (COP)": 10189, Unidad: "litre", "Variación (%)": 0.45 },
  });
  expect(bogota).toMatchObject({
    document_id: sourceId,
    source_locator: expect.stringMatching(/^1!row\s*64,col\s*4(?:; monthly-annex-v[0-9]+)?$/),
    details: { "Precio (COP)": 9458, Unidad: "litre", "Variación (%)": 2.25 },
  });
  const original = await request.get(`/api/evidence/${sourceId}/content`);
  expect(original.ok()).toBeTruthy();
  const bytes = await original.body();
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(sourceId);
  const workbook = test.info().outputPath("dane-aug2026-original.xlsx");
  writeFileSync(workbook, bytes);
  const nativeRow = JSON.parse(execFileSync(path.resolve("../../.venv/bin/python"), ["-c",
    "import json,openpyxl,sys; w=openpyxl.load_workbook(sys.argv[1],read_only=True,data_only=True); print(json.dumps(list(next(w['1'].iter_rows(min_row=64,max_row=64,min_col=1,max_col=5,values_only=True))))); w.close()",
    workbook], { encoding: "utf8", timeout: 10_000 }));
  expect(nativeRow).toEqual(["Aceite vegetal mezcla**", 10189, 0.45, 9458, 2.25]);
  expect(barranquilla.details["Precio (COP)"]).toBe(nativeRow[1]);
  expect(barranquilla.details["Variación (%)"]).toBe(nativeRow[2]);
  expect(bogota.details["Precio (COP)"]).toBe(nativeRow[3]);
  expect(bogota.details["Variación (%)"]).toBe(nativeRow[4]);

  await page.goto("/data-references?kind=wholesale");
  await expect(page.getByRole("heading", { name: "Resumen mayorista mensual" })).toBeVisible();
  await page.getByRole("combobox", { name: "Mes", exact: true }).fill("2026-08-31");
  await page.getByRole("option", { name: /2026-08-31/ }).click();
  await page.getByLabel("Buscar").fill("Aceite vegetal mezcla");
  const card = page.locator("article.panel").filter({ hasText: "Barranquilla" });
  await expect(card).toContainText("Aceite vegetal mezcla**");
  await expect(card).toContainText("10.189");
  await expect(card).toContainText("litro");
  await expect(card.locator("a.evidence-link")).toHaveAttribute("href", new RegExp(sourceId));
  await card.locator("a.evidence-link").click();
  await expect(page.getByRole("dialog", { name: "Documento de la fuente" })).toBeVisible();
  await expect(page.locator(".workbook-viewer")).toContainText("Excel · Solo lectura");
  const cell = page.getByRole("cell", { name: "Celda B64 de la fuente", exact: true });
  await cell.click();
  await expect(cell).toContainText("10.189");
  await page.screenshot({ path: test.info().outputPath("monthly-wholesale-aug2026.png"), fullPage: true });
});
