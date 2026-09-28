import { test, expect } from "@playwright/test";

for (const [query, expected] of [
  ["&region=Quind%C3%ADo", "Quindío"],
  ["&region=", ""],
  ["", "Atlántico"],
]) {
  test(`product link geographic scope ${query || "uses saved preference"}`, async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem(
      "agroamigo-preferences-v2",
      JSON.stringify({ region: "Atlántico", saved: ["limon-tahiti"] }),
    ));
    const requests: string[] = [];
    await page.route("**/api/products/coco?**", async route => {
      const region = new URL(route.request().url()).searchParams.get("region") || "";
      requests.push(region);
      const covered = region !== "Atlántico";
      await route.fulfill({ json: {
        product: { id: "coco", name: "Coco", category: "Frutas", image_key: "coco" },
        markets: [], history: covered ? [{ date: "2023-04-20", price: 48000 }] : [],
        current: covered ? { date: "2023-04-20", price: 48000, market_count: 1 } : null,
        classification: [["Frutas", "Otras frutas"]],
        filters: { series: "city", market: "sipsa-armenia-mercar", presentation: "Docena", units: "15 Kilogramo", history: "all" },
        options: { series: ["city"], presentations: ["Docena"], units: ["15 Kilogramo"], markets: [{ id: "sipsa-armenia-mercar", name: "Armenia, Mercar" }] },
      } });
    });
    await page.goto("/product/coco?series=city&market=sipsa-armenia-mercar&presentation=Docena&units=15+Kilogramo&history=all" + query);
    await expect(page.getByTestId("current-product-price")).toContainText(expected === "Atlántico" ? "Sin reporte" : "48.000");
    await expect.poll(() => requests.at(-1)).toBe(expected);
    await expect.poll(async () => page.evaluate(() => JSON.parse(localStorage.getItem("agroamigo-preferences-v2") || "{}"))).toEqual({ region: expected, saved: ["limon-tahiti"] });
    await expect(page.locator(".applied-filters").first()).toContainText(expected || "Colombia");
  });
}
