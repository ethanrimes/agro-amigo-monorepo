import { expect, test } from "@playwright/test";

test("image credits use a bounded exact choice and retain the image, attribution and navigation", async ({ page }) => {
  await page.goto("/credits");
  const cards = page.locator(".credits-grid article");
  const choice = page.getByRole("group", { name: "Consultar los créditos de una imagen" });
  const search = choice.getByRole("combobox");
  await expect(cards).toHaveCount(0);
  await search.click();
  await expect(choice.getByRole("option")).toHaveCount(8);
  await search.fill("liatris");
  await expect(cards).toHaveCount(0);
  await choice.getByRole("option", { name: /Liatris Spicata 01.jpg/ }).click();
  await expect(choice).toHaveAttribute("data-selected-value", "liatris-cut");
  await expect(cards).toHaveCount(1);
  await expect(cards.getByRole("img")).toHaveAttribute("src", "/images/library/liatris-cut.jpg");
  await expect(cards).toContainText("Marc Ryckaert (MJJR)");
  await expect(cards.getByRole("link", { name: "CC BY 2.5", exact: true })).toHaveAttribute("href", "https://creativecommons.org/licenses/by/2.5");
  await expect(cards.getByRole("link", { name: "Ver origen de la imagen", exact: true })).toHaveAttribute("href", "https://commons.wikimedia.org/wiki/File:Liatris_Spicata_01.jpg");
  await expect(cards).toContainText("Versión local redimensionada");
  await expect.poll(() => cards.getByRole("img").evaluate((img) => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0)).toBe(true);

  await search.fill("no-matching-image-zzzz");
  await expect(choice).toHaveAttribute("data-selected-value", "liatris-cut");
  await expect(cards).toHaveCount(1);
  await search.press("Escape");
  await choice.getByRole("button", { name: "Quitar selección", exact: true }).click();
  await expect(cards).toHaveCount(0);
  await search.fill("cafe pergamino");
  await choice.getByRole("option", { name: /Colombian Parchment Coffee.jpg/ }).click();
  await expect(cards.getByRole("img")).toHaveAttribute("src", "/images/library/coffee-parchment.jpg");
  await expect(cards).toContainText("Felipe Quijano");
  await expect(cards.getByRole("link", { name: "CC BY-SA 4.0", exact: true })).toHaveAttribute("href", "https://creativecommons.org/licenses/by-sa/4.0/");

  const mainNav = page.getByRole("navigation", { name: "Navegación principal", exact: true });
  const mobileNav = page.getByRole("navigation", { name: "Navegación móvil", exact: true });
  const nav = await mobileNav.isVisible() ? mobileNav : mainNav;
  await nav.getByRole("link", { name: "Insumos", exact: true }).click();
  await expect(page).toHaveURL(/\/insumos/);
});
