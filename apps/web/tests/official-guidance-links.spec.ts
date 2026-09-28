import { test, expect } from "@playwright/test";

test("coffee education links to the verified FNC article without presenting it as a current quotation", async ({ page }) => {
  await page.route("**/api/planning/library", route => route.fulfill({ json: [] }));
  await page.goto("/sources");
  const guidance = page.locator(".source-card").filter({ has: page.getByRole("heading", { name: "FNC · Aprende a vender tu café", exact: true }) });
  await expect(guidance.getByRole("link", { name: "Consultar fuente oficial" })).toHaveAttribute(
    "href", "https://nortedesantander.federaciondecafeteros.org/aprenda-a-vender-su-cafe/",
  );
  await expect(guidance).toContainText("Consultar en la fuente");
  await expect(guidance).toContainText("requieren cotizaciones directas");
  await expect(guidance.locator("a")).toHaveAttribute("target", "_blank");
  await expect(guidance.locator("a")).toHaveAttribute("rel", "noreferrer");
  // An educational article's historical factor is not imported into price data.
  await expect(guidance).not.toContainText("94");
  await expect(page.locator('.source-card a[href="https://federaciondecafeteros.org/precio-del-cafe/"]')).toHaveCount(1);
});
