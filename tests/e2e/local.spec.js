const { test, expect } = require("@playwright/test");
const {
  capturedEmails,
  capturedRecords,
  loginAdmin,
  relativePathFromCapturedUrl,
  resetE2E,
} = require("./helpers");

test.beforeEach(async ({ request }) => {
  await resetE2E(request);
});

test("diners discover specials, use action links, receive digest, and unsubscribe", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Today's specials/i })).toBeVisible();
  await expect(page.getByTestId("special-card").filter({ hasText: "E2E Halibut Sandwich" })).toBeVisible();

  await page.locator('select[name="city"]').selectOption("Mount Vernon");
  await expect(page.getByTestId("special-card").filter({ hasText: "E2E Halibut Sandwich" })).toBeVisible();

  await page.getByTestId("special-card").filter({ hasText: "E2E Halibut Sandwich" }).getByTestId("special-card-action").click();
  await expect(page).toHaveURL(/\/specials\//);

  for (const testId of ["special-action-directions", "special-action-call", "special-action-website", "special-action-share"]) {
    const href = await page.getByTestId(testId).getAttribute("href");
    const response = await request.get(href, { maxRedirects: 0 });
    expect([302, 303]).toContain(response.status());
  }

  await page.getByRole("link", { name: "View restaurant" }).click();
  await expect(page.getByRole("heading", { name: "E2E Test Kitchen", exact: true })).toBeVisible();
  await page.getByPlaceholder("you@example.com").fill("follower@example.com");
  await page.getByRole("button", { name: "Notify me" }).click();
  await expect(page.getByText(/You're following E2E Test Kitchen/)).toBeVisible();

  await loginAdmin(page);
  await page.goto("/admin/diner-digest");
  await expect(page.getByText("E2E Halibut Sandwich", { exact: true })).toBeVisible();
  await page.getByTestId("send-test-digest").click();
  await expect(page.getByText(/Sent diner digest test to e2e-digest@example.com/)).toBeVisible();

  page.on("dialog", (dialog) => dialog.accept());
  await page.getByTestId("send-production-digest").click();
  await expect(page.getByText(/Sent diner digest to 2 Skagit subscribers/)).toBeVisible();

  const emails = await capturedEmails(request);
  const testDigest = emails.find((email) => email.to === "e2e-digest@example.com");
  const productionDigest = emails.find((email) => email.to === "skagit@example.com");
  expect(testDigest?.subject).toContain("good today in Skagit Valley");
  expect(productionDigest?.text).toContain("channel=email_digest");
  expect(productionDigest?.tags).toEqual([{ name: "channel", value: "email_digest" }]);
  expect(emails.some((email) => email.to === "seattle@example.com")).toBeFalsy();
  expect(emails.some((email) => email.to === "unsubscribed@example.com")).toBeFalsy();

  const unsubscribeUrl = new URL(productionDigest.text.match(/Unsubscribe: (https?:\/\/\S+)/)[1]);
  const unsubscribePath = unsubscribeUrl.pathname + unsubscribeUrl.search;
  await page.goto(unsubscribePath);
  await expect(page.getByText(/unsubscribed/i)).toBeVisible();
});

test("restaurant public submission sends approval email, publishes, and grants operator tools", async ({ page, request }) => {
  await page.goto("/submit-special");
  await page.getByLabel("Restaurant").fill("E2E");
  await page.getByTestId("restaurant-result-included").filter({ hasText: "E2E Test Kitchen" }).click();
  await page.getByLabel("Special details").fill("Tonight only, browser test oysters for $15, 4-8pm.");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByRole("button", { name: "Send special" }).click();
  await expect(page.getByRole("heading", { name: /Special received/i })).toBeVisible();

  const approvalEmail = (await capturedEmails(request)).find((email) => email.to === "owner@example.com");
  expect(approvalEmail?.subject).toBe("We received your special");
  expect(approvalEmail.text).toContain("browser test oysters");
  const previewPath = relativePathFromCapturedUrl(approvalEmail.text);

  await page.goto(previewPath);
  await expect(page.getByRole("heading", { name: "Review your special" })).toBeVisible();
  await page.getByTestId("preview-publish").click();
  await expect(page.getByText("Operator tools")).toBeVisible();
  await expect(page.getByTestId("sold-out-button")).toBeVisible();
  await page.getByTestId("sold-out-button").click();
  await expect(page.getByText(/Special marked sold out/)).toBeVisible();
});

test("private links, trusted publishing, admin publishing, distribution, and outreach capture emails", async ({ page, request }) => {
  await loginAdmin(page);

  await page.goto("/admin/restaurants/1/edit");
  await page.getByRole("button", { name: "Generate link" }).click();
  const privateUrl = await page.locator("input[readonly]").inputValue();
  await page.goto(new URL(privateUrl).pathname);
  await page.getByLabel("Title").fill("Private Link Pasta");
  await page.getByLabel("Description").fill("Handmade pasta from the browser flow.");
  await page.getByLabel("Price").fill("$19");
  await page.getByLabel(/Email/).fill("owner@example.com");
  await page.getByLabel("Date").fill("2099-06-05");
  await page.getByRole("button", { name: "Send special" }).click();
  await expect(page.getByRole("heading", { name: /Special received/i })).toBeVisible();

  await page.goto("/admin/special-drafts");
  await page.getByTestId("draft-card").filter({ hasText: "Private Link Pasta" }).getByTestId("send-publish-email").click();
  await expect(page.getByText(/Publish email sent/)).toBeVisible();
  const publishEmail = (await capturedEmails(request)).find((email) => email.to === "owner@example.com");
  expect(publishEmail?.text).toContain("/specials/preview/");

  await page.goto("/admin/restaurants/2/edit");
  await page.getByRole("button", { name: "Generate link" }).click();
  const trustedUrl = await page.locator("input[readonly]").inputValue();
  await page.goto(new URL(trustedUrl).pathname);
  await page.getByLabel("Title").fill("Trusted Taco Lunch");
  await page.getByLabel("Description").fill("Fast-published tacos.");
  await page.getByLabel("Price").fill("$12");
  await page.getByLabel("Date").fill("2099-06-05");
  await page.getByRole("button", { name: "Send special" }).click();
  await expect(page.getByText("It's live now.")).toBeVisible();
  const trustedEmails = (await capturedEmails(request)).filter((email) => email.to === "trusted@example.com");
  expect(trustedEmails.some((email) => email.subject === "We received your special")).toBeFalsy();
  expect(trustedEmails.some((email) => email.subject === "Next time you run a special.")).toBeTruthy();

  await page.goto("/admin/specials/new");
  await page.locator('select[name="restaurant_id"]').selectOption({ label: "E2E Test Kitchen" });
  await page.locator('input[name="title"]').fill("Admin Browser Dinner");
  await page.locator('textarea[name="description"]').fill("A manually published browser dinner.");
  await page.locator('input[name="price"]').fill("$22");
  await page.locator('input[name="special_date"]').fill("2099-06-05");
  await page.locator('select[name="status"]').selectOption("published");
  await page.locator('input[name="enhance"]').uncheck();
  await page.getByRole("button", { name: "Create enhanced draft" }).click();
  await expect(page.getByRole("heading", { name: "Edit special" })).toBeVisible();
  await page.goto("/admin/specials");
  await page.getByRole("link", { name: "Distribution kit" }).first().click();
  await expect(page.getByText("Tracked links")).toBeVisible();
  await page.getByLabel("Social caption").fill("Posted from browser E2E.");
  await page.locator('select[name="channel"]').selectOption("facebook_page");
  await page.getByPlaceholder("Optional note").fill("Launch browser test");
  await page.getByRole("button", { name: "Mark posted" }).click();
  await expect(page.getByText("Launch browser test")).toBeVisible();

  await page.goto("/admin/outreach");
  await page.getByRole("row", { name: /Outreach Bistro/ }).getByRole("button", { name: "Enroll" }).click();
  await expect(page.getByRole("heading", { name: "Outreach Bistro", exact: true })).toBeVisible();
  await page.getByLabel("Subject").fill("Browser outreach");
  await page.getByLabel("Body").fill("Reviewed outreach from the browser.");
  await page.getByLabel("Reviewed and ready to send").check();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Send reviewed email" }).click();
  await expect(page.getByText(/outbound.*sent/i)).toBeVisible();

  const records = await capturedRecords(request);
  expect(records.some((record) => record.kind === "email" && record.to === "outreach@example.com")).toBeTruthy();
  expect(records.some((record) => record.kind === "loops_contact" && record.email === "outreach@example.com")).toBeTruthy();
  expect(records.some((record) => record.kind === "loops_event" && record.event_name === "founderOutreachSent")).toBeTruthy();
});
