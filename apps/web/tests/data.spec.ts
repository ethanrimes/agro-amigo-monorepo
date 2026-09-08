import { test, expect } from "@playwright/test";
test("Unified catalog preserves dated source identities and exact detail prices", async ({
  request,
}) => {
  test.setTimeout(90000);
  expect((await request.get("/api/health")).ok()).toBeTruthy();
  const catalog = await (await request.get("/api/catalog")).json();
  expect(catalog.products.length).toBeGreaterThan(100);
  expect(new Set(catalog.products.map((p: any) => p.identity)).size).toBe(catalog.products.length);
  expect(new Set(catalog.products.map((p: any) => p.saved_key)).size).toBe(catalog.products.length);
  for (const p of catalog.products) {
    expect(p.price).toBeGreaterThan(0);
    expect(p.unit).toBeTruthy();
    expect(p.source).toBeTruthy();
    expect(p.currency).toMatch(/^[A-Z]{3}$/);
    expect(p.basis).toBeTruthy();
    expect(p.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(p.href).toMatch(/^\/(product|references)\//);
    if (p.kind === "official-reference") {
      expect(p.saved_key).toBe("reference:" + p.quote_key);
      expect(p.href).toBe("/references/" + p.quote_key);
      expect(p.map_supported).toBe(false);
    } else {
      expect(p.identity).toBe(p.id);
      expect(p.saved_key).toBe(p.id);
      expect(new URL(p.href, "https://example.test").searchParams.get("region")).toBe("");
    }
  }
  const search = catalog.products.flatMap((p: any) => [p.name, ...p.search_terms]).join(" ")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  for (const family of ["arabica", "robusta", "cacao", "banano", "rosa", "palma", "coco", "azucar", "cerdo", "leche", "arroz"]) {
    expect(search).toContain(family);
  }
  const references = await (await request.get("/api/references")).json();
  expect(catalog.products.filter((p: any) => p.kind === "official-reference" && !p.quote_key.startsWith("summary-")).length).toBe(references.total);
  expect(catalog.products.some((p: any) => p.name === "Tomate*" && p.quote_key?.startsWith("summary-"))).toBeTruthy();
  const selected = catalog.products.find((p: any) => p.id === "aguacate-hass");
  const detail = await (
    await request.get("/api/products/" + selected.id + "?" + selected.href.split("?")[1])
  ).json();
  expect(detail.markets.length).toBeGreaterThan(0);
  expect(
    detail.markets.every((m: any) =>
      m.source_url.startsWith("https://www.dane.gov.co/"),
    ),
  ).toBeTruthy();
  expect(detail.current.price).toBeCloseTo(selected.price, 7);
  expect(detail.current.date).toBe(selected.date);
  for (const series of ["farmgate", "mill", "city"]) {
    const p = catalog.products.find((p: any) => p.series === series);
    expect(p).toBeTruthy();
    const response = await request.get("/api/products/" + p.id + "?" + p.href.split("?")[1]);
    expect(response.ok()).toBeTruthy();
    const exact = await response.json();
    expect(exact.current.price).toBeCloseTo(p.price, 7);
    expect(exact.current.date).toBe(p.date);
    expect(exact.filters.series).toBe(series);
    expect(exact.filters.presentation).toBe(p.presentation);
    expect(exact.filters.units).toBe(p.units);
  }
  const summary = catalog.products.find((p: any) => p.name === "Tomate*" && p.quote_key?.startsWith("summary-"));
  const summaryDetail = await (await request.get("/api/references?id=" + summary.quote_key)).json();
  expect(summaryDetail.reference.price).toBe(summary.price);
  expect(summaryDetail.reference.unit).toBe(summary.unit);
  expect(summaryDetail.reference.market).toBe(summary.market);
  expect(summaryDetail.reference.observed_on).toBe(summary.date);
  const coffee = await (await request.get("/api/coffee")).json();
  const catalogCoffee = catalog.products.find((p: any) => p.id === "cafe-pergamino-seco");
  expect(catalogCoffee.price).toBe(coffee.price);
  expect(catalogCoffee.date).toBe(coffee.date);
  expect(catalogCoffee.unit).toBe("125kg");
  expect(coffee.history.length).toBeGreaterThan(250);
  expect(coffee.markets.length).toBe(16);
  expect(coffee.factors.length).toBe(13);
  expect(coffee.exchange.price).toBeGreaterThan(0);
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const cutoff = `${Number(today.slice(0, 4)) - 1}${today.slice(4)}`;
  for (const product of catalog.products) expect(product.date <= today).toBeTruthy();
  for (const row of [...coffee.history, ...detail.history]) {
    expect(row.date > cutoff).toBeTruthy();
    expect(row.date <= today).toBeTruthy();
  }
  const noRegion = await (
    await request.get("/api/catalog?region=region-does-not-exist")
  ).json();
  expect(noRegion.products).toEqual([]);
  expect(noRegion.filters.reference_scope).toBe("regional-only");
  expect(noRegion.filters.excluded_nonregional_count).toBeGreaterThan(0);
  expect(noRegion.filters.excluded_nonregional_reason).toContain("filtro de departamento");
  expect((await request.get("/api/products/does-not-exist")).status()).toBe(
    404,
  );
});
