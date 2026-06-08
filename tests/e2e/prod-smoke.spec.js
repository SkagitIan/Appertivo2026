const { test, expect } = require("@playwright/test");

test("production public launch smoke is read-only", async ({ page, request, baseURL }) => {
  const health = await request.get("/health");
  expect(health.ok()).toBeTruthy();

  await page.goto("/");
  await expect(page.getByText("Appertivo").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /View special/i }).first()).toBeVisible();

  await page.goto("/restaurants");
  await expect(page).toHaveURL(/\/specials/);

  await page.goto(baseURL);
  await page.getByRole("link", { name: /View special/i }).first().click();
  await expect(page).toHaveURL(/\/specials\//);
});
