import { test, expect } from "@playwright/test";
import {
  compareQuotes,
  summarizeComparisons,
} from "../src/lib/comparison-math";
import type { ComparisonQuote } from "../src/lib/comparison-types";

const quote = (fields: Partial<ComparisonQuote> = {}): ComparisonQuote => ({
  id: "mora",
  name: "Mora de castilla",
  category: "Frutas",
  category_path: ["Frutas", "Otras frutas"],
  presentation: "Caja de cartón",
  units: "2.5 Kilogramo",
  unit: "kg",
  series: "city",
  location_id: "a",
  location_name: "A",
  price: 20_000,
  date: "2026-09-07",
  document_id: "a".repeat(64),
  source_locator: "PDF page 1",
  ...fields,
});

test("comparison only matches exact commercial identity and units", () => {
  const a = quote();
  const matches = compareQuotes(
    [a],
    [
      quote({ units: "12.5 Kilogramo", price: 80_000 }),
      quote({ presentation: "Canastilla" }),
      quote({ series: "monthly" }),
      quote({ unit: "litre" }),
      quote({ brand: "Otra marca" }),
      quote({ registration: "12" }),
      quote({ price: 0 }),
    ],
    false,
  );
  expect(matches[0].b).toBeNull();
  expect(matches[0].percent).toBeNull();
});

test("national average preserves date range and same-date matching excludes older quotes", () => {
  const a = quote({ price: 100 });
  const b = [
    quote({ location_id: "b", price: 120 }),
    quote({ location_id: "c", price: 160, date: "2026-09-04" }),
  ];
  const latest = compareQuotes([a], b, false, true)[0];
  expect(latest.b).toMatchObject({
    price: 140,
    date_from: "2026-09-04",
    date_to: "2026-09-07",
    location_count: 2,
  });
  expect(latest.b?.sources).toHaveLength(2);
  expect(latest.percent).toBe(40);
  const same = compareQuotes([a], b, true)[0];
  expect(same.b).toMatchObject({ price: 120, location_count: 1 });
  expect(same.percent).toBe(20);
  expect(compareQuotes([a], [a], false, false, true)[0].b).toBeNull();
  const duplicate = quote({
    location_id: "b",
    price: 999,
    presentation: "Caja de cartÓn",
    date: "2026-08-01",
  });
  expect(compareQuotes([a], [...b, duplicate], false)[0].b).toMatchObject({
    price: 140,
    location_count: 2,
  });
});

test("category and overall differences are unweighted means of matched percentages", () => {
  const a = [
    quote({ price: 100 }),
    quote({ id: "limon", price: 1000, category_path: ["Frutas", "Cítricos"] }),
    quote({ id: "unmatched" }),
  ];
  const b = [
    quote({ price: 200 }),
    quote({ id: "limon", price: 900, category_path: ["Frutas", "Cítricos"] }),
  ];
  const summary = summarizeComparisons(compareQuotes(a, b, false));
  expect(summary).toMatchObject({ matched: 2, unmatched: 1, percent: 45 });
  expect(summary.summaries.find((g) => g.subcategory === null)).toMatchObject({
    category: "Frutas",
    count: 2,
    percent: 45,
  });
  expect(
    summary.summaries.find((g) => g.subcategory === "Cítricos")?.percent,
  ).toBe(-10);
});

test("city comparison serves both mora package sizes and auditable national prices", async ({
  request,
}) => {
  const response = await request.get(
    "/api/compare/markets?a=sipsa-barranquilla-barranquillita&series=city&product=mora-de-castilla&sources=true",
  );
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.a_name).toContain("Barranquillita");
  const packages = data.rows.filter(
    (r: { a: ComparisonQuote }) =>
      r.a.presentation.toLocaleLowerCase("es") === "caja de cartón",
  );
  expect(
    packages.find((r: { a: ComparisonQuote }) => r.a.units === "2.5 Kilogramo")
      ?.a.price,
  ).toBe(21000);
  expect(
    packages.find((r: { a: ComparisonQuote }) => r.a.units === "12.5 Kilogramo")
      ?.a.price,
  ).toBe(79500);
  for (const row of data.rows) {
    if (!row.b) continue;
    expect(
      row.b.sources.every(
        (q: ComparisonQuote) =>
          q.units.toLowerCase() === row.a.units.toLowerCase() &&
          q.presentation.toLowerCase() === row.a.presentation.toLowerCase(),
      ),
    ).toBeTruthy();
    const mean =
      row.b.sources.reduce(
        (sum: number, q: ComparisonQuote) => sum + q.price,
        0,
      ) / row.b.sources.length;
    expect(row.b.price).toBeCloseTo(mean, 8);
  }
});

test("market comparison filters stay visible and category summaries follow them", async ({
  page,
}) => {
  await page.goto(
    "/compare/markets?a=sipsa-barranquilla-barranquillita&series=city",
  );
  await expect(page.getByLabel("Resultado de la comparación")).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Buscar producto", exact: true })
    .fill("mora");
  await page
    .getByRole("combobox", { name: "Unidades", exact: true })
    .selectOption("2.5 Kilogramo");
  const applied = page.getByLabel("Filtros aplicados");
  await expect(applied).toContainText("Barranquillita");
  await expect(applied).toContainText("mora");
  await expect(applied).toContainText("2.5 Kilogramo");
  await expect(page.getByLabel("Resultado de la comparación")).toContainText(
    "1 combinaciones de A bajo los filtros",
  );
  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("article")).toContainText("21.000");
  await expect(page.locator("body")).not.toHaveJSProperty("scrollWidth", 0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBeFalsy();
});

test("market price list expands, collapses and maintains exact filter links", async ({
  page,
}) => {
  await page.goto("/market/sipsa-barranquilla-barranquillita");
  await expect(
    page.getByRole("button", { name: "Expandir lista completa", exact: true }),
  ).toBeVisible();
  const before = await page.getByRole("article").count();
  await page
    .getByRole("button", { name: "Expandir lista completa", exact: true })
    .click();
  expect(await page.getByRole("article").count()).toBeGreaterThan(before);
  await page
    .getByRole("button", { name: "Mostrar menos", exact: true })
    .click();
  await expect(page.getByRole("article")).toHaveCount(before);
  await page
    .getByRole("searchbox", { name: "Buscar producto", exact: true })
    .fill("limón tahití");
  const link = page
    .getByRole("link", { name: "Limón tahití", exact: true })
    .first();
  await expect(link).toHaveAttribute(
    "href",
    /market=sipsa-barranquilla-barranquillita.*series=city.*presentation=.*units=/,
  );
});
