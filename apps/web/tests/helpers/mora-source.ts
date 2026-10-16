import { expect, type APIRequestContext } from "@playwright/test";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import type { ComparisonQuote } from "../../src/lib/comparison-types";

const months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function moraPageRow(pageText: string, units: string, round: number) {
  const text = pageText.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es");
  expect(text).toContain("barranquilla, barranquillita");
  const printedDate = text.match(/\b(\d{1,2}) de ([a-z]+) de (\d{4})\b/);
  expect(printedDate, "printed city bulletin date").not.toBeNull();
  const month = months.indexOf(printedDate![2]) + 1;
  expect(month).toBeGreaterThan(0);
  const date = `${printedDate![3]}-${String(month).padStart(2, "0")}-${printedDate![1].padStart(2, "0")}`;
  const rows = text.split(/\r?\n/).filter(line => /^\s*mora de castilla\s+caja de carton\s+/.test(line));
  const matching = rows.filter(line => new RegExp(`\\s${units.replace(".", "\\.")}\\s+kilogramo\\s`).test(line));
  expect(matching, `one original Mora carton row for ${units}`).toHaveLength(1);
  const fields = matching[0].match(/^\s*mora de castilla\s+caja de carton\s+(\d+(?:\.\d+)?)\s+kilogramo\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$/);
  expect(fields, `original price columns for ${units}`).not.toBeNull();
  expect(fields![1]).toBe(units);
  const pair = round === 1 ? fields!.slice(2, 4) : fields!.slice(4, 6);
  return { date, min: Number(pair[0].replaceAll(".", "")), max: Number(pair[1].replaceAll(".", "")) };
}

/** Independent native-PDF oracle; neither parser tables nor UI provide its money/date. */
export async function verifyMoraQuote(request: APIRequestContext, current: ComparisonQuote) {
  expect(current.document_id).toMatch(/^[a-f0-9]{64}$/);
  const locator = current.source_locator?.match(/^PDF page (\d+),table (\d+),row (\d+),round ([12])$/);
  expect(locator, "exact original row and round").not.toBeNull();
  expect(Number(locator![2])).toBe(1);
  expect(Number(locator![3])).toBeGreaterThan(0);
  const sourcePage = Number(locator![1]);
  expect(current.source_page).toBe(sourcePage);
  const original = await request.get(`/api/evidence/${current.document_id}/content`);
  expect(original.ok()).toBeTruthy();
  expect(original.headers()["content-type"]).toContain("application/pdf");
  const bytes = await original.body();
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(current.document_id);
  const text = execFileSync("pdftotext", ["-layout", "-f", String(sourcePage), "-l", String(sourcePage), "-", "-"],
    { input: bytes, encoding: "utf8", timeout: 10_000, maxBuffer: 2_000_000 });
  const printed = moraPageRow(text, current.units.split(" ")[0], Number(locator![4]));
  expect(current).toMatchObject({ date: printed.date, min_price: printed.min, max_price: printed.max, presentation: "Caja de cartón" });
  expect(current.price).toBe((printed.min + printed.max) / 2);
  return current;
}

export async function latestMoraPackages(request: APIRequestContext) {
  const response = await request.get("/api/compare/markets?a=sipsa-barranquilla-barranquillita&series=city&product=mora-de-castilla&sources=true");
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  const result = new Map<string, ComparisonQuote>();
  for (const units of ["2.5 Kilogramo", "12.5 Kilogramo"]) {
    const current = data.rows.find((row: { a: ComparisonQuote }) => row.a.units === units && row.a.presentation === "Caja de cartón")?.a;
    expect(current, `${units} source-backed latest price`).toBeDefined();
    result.set(units, await verifyMoraQuote(request, current));
  }
  return result;
}
