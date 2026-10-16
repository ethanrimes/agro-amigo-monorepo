import { expect, test } from "@playwright/test";

const cases = [
  {
    id: "wage-monthly-context",
    product: "Mensual agrícola sin alimentación",
    market: "Duitama",
    expected: "Pago mensual · sin alimentación",
  },
  {
    id: "wage-weekly-context",
    product: "Semanal agrícola con alimentación",
    market: "Manizales",
    expected: "Pago semanal · con alimentación",
  },
];

test("wage source view explains consultation presentation while preserving source wording and query", async ({ page }) => {
  const requests: URL[] = [];
  for (const row of cases) {
    await page.route(`**/api/evidence/${row.id}**`, async (route) => {
      const url = new URL(route.request().url());
      requests.push(url);
      await route.fulfill({ json: {
        id: row.id,
        title: `DANE · fuente laboral ${row.market}`,
        publisher: "DANE",
        kind: "original",
        media_type: "application/json",
        source_url: "https://www.dane.gov.co/",
        reference_period: "2012",
        retrieved_at: "2026-10-12T00:00:00Z",
        bytes: 100,
        page_count: null,
        metadata: { query_context: [
          { label: "Producto de la consulta", value: row.product },
          { label: "Presentación de la consulta", value: "Jornal" },
          { label: "Presentación en la fuente", value: "Jornal" },
          { label: "Mercado de la consulta", value: row.market },
        ] },
        records: [],
        parents: [],
      } });
    });

    const query = new URLSearchParams({
      productName: row.product,
      presentation: "Jornal",
      municipality: row.market,
      month: "2012-09-30",
    });
    await page.goto(`/evidence/${row.id}?${query.toString()}`);

    const filters = page.getByLabel("Filtros de los datos consultados", { exact: true });
    await expect(filters).toContainText(`Producto de la consulta: ${row.product}`);
    await expect(filters).toContainText(`Presentación de la consulta: ${row.expected}`);
    await expect(filters).toContainText(`Presentación en la fuente: Jornal`);
    await expect(filters).toContainText(`Mercado de la consulta: ${row.market}`);
    await expect(filters).toContainText("Fecha del dato consultado: 2012-09-30");

    const request = requests.find((candidate) => candidate.pathname === `/api/evidence/${row.id}`);
    expect(request).toBeDefined();
    expect(request!.searchParams.get("productName")).toBe(row.product);
    expect(request!.searchParams.get("presentation")).toBe("Jornal");
    expect(request!.searchParams.get("municipality")).toBe(row.market);
    expect(request!.searchParams.get("month")).toBe("2012-09-30");
  }
});

test("unrelated non-wage source context keeps its original presentation", async ({ page }) => {
  const id = "non-wage-context";
  await page.route(`**/api/evidence/${id}**`, (route) => route.fulfill({ json: {
    id,
    title: "DANE · original de insumos",
    publisher: "DANE",
    kind: "original",
    media_type: "application/json",
    source_url: "https://www.dane.gov.co/",
    reference_period: "2012",
    retrieved_at: "2026-10-12T00:00:00Z",
    bytes: 100,
    page_count: null,
    metadata: { query_context: [
      { label: "Producto de la consulta", value: "Wuxal" },
      { label: "Presentación de la consulta", value: "Jornal" },
      { label: "Presentación en la fuente", value: "Jornal" },
    ] },
    records: [],
    parents: [],
  } }));

  await page.goto(`/evidence/${id}?${new URLSearchParams({ productName: "Wuxal", presentation: "Jornal" })}`);
  const filters = page.getByLabel("Filtros de los datos consultados", { exact: true });
  await expect(filters).toContainText("Producto de la consulta: Wuxal");
  await expect(filters).toContainText("Presentación de la consulta: Jornal");
  await expect(filters).toContainText("Presentación en la fuente: Jornal");
});
