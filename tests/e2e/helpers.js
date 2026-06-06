const { expect } = require("@playwright/test");

async function resetE2E(request) {
  const response = await request.get("/__e2e/reset");
  expect(response.ok()).toBeTruthy();
}

async function capturedRecords(request) {
  const response = await request.get("/__e2e/capture");
  expect(response.ok()).toBeTruthy();
  return (await response.json()).records;
}

async function capturedEmails(request) {
  return (await capturedRecords(request)).filter((record) => record.kind === "email");
}

async function loginAdmin(page) {
  await page.goto("/admin/login");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

function relativePathFromCapturedUrl(text) {
  const match = text.match(/https?:\/\/[^\s"'<>]+(\/specials\/preview\/[a-f0-9]+)/i);
  if (!match) {
    throw new Error(`No preview URL found in captured text: ${text}`);
  }
  return match[1];
}

module.exports = {
  capturedEmails,
  capturedRecords,
  loginAdmin,
  relativePathFromCapturedUrl,
  resetE2E,
};

