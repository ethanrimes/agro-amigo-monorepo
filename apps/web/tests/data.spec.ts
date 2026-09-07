import { test, expect } from "@playwright/test";
test("Azure API returns real, dated sources and only the demo window", async ({
  request,
}) => {
  expect((await request.get("/api/health")).ok()).toBeTruthy();
  const catalog = await (await request.get("/api/catalog")).json();
  expect(catalog.products.length).toBeGreaterThan(100);
  expect(
    catalog.products.every(
      (p: any) => p.price > 0 && p.unit === "kg" && p.period === "monthly",
    ),
  ).toBeTruthy();
  const selected = catalog.products[0];
  const detail = await (
    await request.get("/api/products/" + selected.id)
  ).json();
  expect(detail.markets.length).toBeGreaterThan(0);
  expect(
    detail.markets.every((m: any) =>
      m.source_url.startsWith("https://www.dane.gov.co/"),
    ),
  ).toBeTruthy();
  const coffee = await (await request.get("/api/coffee")).json();
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
  for (const row of [...coffee.history, ...detail.history]) {
    expect(row.date > cutoff).toBeTruthy();
    expect(row.date <= today).toBeTruthy();
  }
  const noRegion = await (
    await request.get("/api/catalog?region=region-does-not-exist")
  ).json();
  expect(noRegion.products).toEqual([]);
  expect((await request.get("/api/products/does-not-exist")).status()).toBe(
    404,
  );
});
