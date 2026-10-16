import { expect, test } from "@playwright/test";

const firstMarket = {
  id: "dane-city-manizales-centro-galerias",
  name: "Manizales, Centro Galerías",
  literal_name: "Manizales, Centro Galerias",
  first_report_on: "2021-12-16",
  last_report_on: "2022-02-03",
};
const secondMarket = {
  id: "sipsa-manizales-centro-galerias",
  name: "Manizales, Centro Galerías",
  literal_name: "Manizales, Centro Galerías",
  first_report_on: "2020-03-26",
  last_report_on: "2026-10-08",
};

test("duplicate city-market labels expose source identity and keep the chosen history ID", async ({ page }) => {
  const requested: URLSearchParams[] = [];
  await page.route("**/api/products/carne-de-res-bola-de-brazo?**", (route) => {
    const query = new URL(route.request().url()).searchParams;
    requested.push(new URLSearchParams(query));
    const market = query.get("market") || "";
    const selected = market === secondMarket.id ? secondMarket : firstMarket;
    // Deliberately distinct fixture values make a stale response from the other
    // same-label market visible; these are test data, not source-price claims.
    const current = market === firstMarket.id
      ? { date: "2022-02-03", price: 14_100, market_count: 1 }
      : market === secondMarket.id
        ? { date: "2026-10-08", price: 19_250, market_count: 1 }
        : null;
    return route.fulfill({ json: {
      product: { id: "carne-de-res-bola-de-brazo", name: "Carne de res, bola de brazo", category: "Carnes", image_key: "produce" },
      markets: current ? [{ id: selected.id, name: selected.name, city: "Manizales",
        region: "Caldas", price: current.price, min_price: current.price - 750, max_price: current.price + 750,
        date: current.date, source_url: "https://example.invalid/source.pdf",
        document_id: "a".repeat(64), source_locator: "PDF page 1,table 1,row 7,round 1",
        period: "daily", unit: "kg", presentation: "Kilogramo", units: "1 Kilogramo", series: "city" }] : [],
      history: current
        ? [{
            date: current.date,
            price: current.price,
            market_count: 1,
            sources: [{
              document_id: "a".repeat(64),
              source_locator: "PDF page 1,table 1,row 7,round 1",
              source_page: 1,
              market_id: selected.id,
              market_name: selected.literal_name,
              source_units: "1 Kilogramo",
            }],
          }]
        : [],
      current,
      classification: [["Carnes", "Carne de res"]],
      additional_references: [],
      filters: { region: "Caldas", series: "city", market, presentation: "Kilogramo",
        units: "1 Kilogramo", history: "all" },
      options: { series: ["city"], presentations: ["Kilogramo"], units: ["1 Kilogramo"],
        markets: [firstMarket, secondMarket] },
    } });
  });

  await page.goto("/product/carne-de-res-bola-de-brazo?region=Caldas&series=city&presentation=Kilogramo&units=1+Kilogramo&history=all");
  const market = page.getByRole("group", { name: "Mercado", exact: true });
  const search = market.getByRole("combobox", { name: "Mercado", exact: true });
  await search.fill("Manizales");

  const options = market.getByRole("option");
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toContainText("Informes: 16/12/2021–03/02/2022");
  await expect(options.nth(0)).toContainText("Nombre en la fuente: Manizales, Centro Galerias");
  await expect(options.nth(1)).toContainText("Informes: 26/03/2020–08/10/2026");
  await expect(options.nth(1)).toContainText("Nombre en la fuente: Manizales, Centro Galerías");

  await options.nth(0).click();
  await expect(market).toHaveAttribute("data-selected-value", firstMarket.id);
  await expect(market.getByRole("status")).toContainText("16/12/2021–03/02/2022");
  await expect(market.getByRole("status")).toContainText("Nombre en la fuente: Manizales, Centro Galerias");
  await expect(page.getByTestId("current-product-price")).toContainText("14.100");
  await expect(page.locator(".product-price-header small")).toContainText("3 de febrero de 2022");
  await expect.poll(() => requested.some((query) => query.get("market") === firstMarket.id)).toBe(true);
  expect(new URL(page.url()).searchParams.get("market")).toBe(firstMarket.id);

  await search.fill("manizales, centro galerias");
  await expect(options).toHaveCount(2);
  await expect(options.nth(0)).toContainText("Nombre en la fuente: Manizales, Centro Galerias");
  await expect(options.nth(1)).toContainText("Nombre en la fuente: Manizales, Centro Galerías");
  await options.nth(1).click();
  await expect(market).toHaveAttribute("data-selected-value", secondMarket.id);
  await expect(market.getByRole("status")).toContainText("Manizales, Centro Galerías");
  await expect(market.getByRole("status")).toContainText("26/03/2020–08/10/2026");
  await expect(market.getByRole("status")).toContainText("Nombre en la fuente: Manizales, Centro Galerías");
  await expect(page.getByTestId("current-product-price")).toContainText("19.250");
  await expect(page.locator(".product-price-header small")).toContainText("8 de octubre de 2026");
  expect(new URL(page.url()).searchParams.get("market")).toBe(secondMarket.id);
  await expect.poll(() => requested.some((query) => query.get("market") === secondMarket.id)).toBe(true);
});
