import { test, expect } from "@playwright/test";

test("catalog cards preserve their contents through scrolling and expansion", async ({
  page,
  isMobile,
}) => {
  test.setTimeout(90_000);
  await page.goto("/products");
  const cards = page.locator(".product-grid > .product-card");
  await expect(cards).toHaveCount(24);
  const first = cards.first();
  await expect(first.locator(".product-name")).toHaveText("Café pergamino seco");
  const firstPrice = await first.locator(".product-price").innerText();
  for (const index of [0, 2, 8, 16, 23, 8, 2, 0]) {
    await cards.nth(index).scrollIntoViewIfNeeded();
    expect(
      await cards.nth(index).evaluate((card) => {
        const bounds = card.getBoundingClientRect();
        const image = card.querySelector(".product-image-link")!.getBoundingClientRect();
        const body = card.querySelector(".product-card-body")!.getBoundingClientRect();
        const price = card.querySelector(".product-price")!.getBoundingClientRect();
        const footer = card.querySelector(".product-card-footer")!.getBoundingClientRect();
        return (
          body.top >= image.bottom - 1 &&
          price.top >= body.top &&
          footer.top >= price.bottom - 1 &&
          footer.bottom <= bounds.bottom + 1 &&
          body.left >= bounds.left &&
          body.right <= bounds.right
        );
      }),
    ).toBe(true);
  }
  // Real touch browsers can retain :hover after a tap. Such cards must stay static.
  await first.hover();
  if (isMobile) {
    expect(await first.evaluate((el) => getComputedStyle(el).transform)).toBe("none");
    expect(
      await first.locator("img").evaluate((el) => getComputedStyle(el).transform),
    ).toBe("none");
  } else {
    await expect.poll(() => first.evaluate((el) => getComputedStyle(el).transform)).not.toBe("none");
  }
  await page.getByRole("button", { name: /^Ver más productos/ }).click();
  await expect(cards).toHaveCount(48);
  await expect(first.locator(".product-price")).toHaveText(firstPrice);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
