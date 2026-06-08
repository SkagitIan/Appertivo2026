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
  await page.getByLabel("Special details").fill("Private Link Pasta. Handmade pasta from the browser flow for $19.");
  await page.getByRole("button", { name: "Send special" }).click();
  await expect(page.getByRole("heading", { name: /Special received/i })).toBeVisible();

  await page.goto("/admin/special-drafts");
  await page.getByTestId("draft-card").filter({ hasText: "Private Link Pasta" }).getByTestId("draft-preview-link").click();
  await page.getByTestId("preview-publish").click();
  await expect(page.getByText("Operator tools")).toBeVisible();

  await page.goto("/admin/restaurants/2/edit");
  await page.getByRole("button", { name: "Generate link" }).click();
  const trustedUrl = await page.locator("input[readonly]").inputValue();
  await page.goto(new URL(trustedUrl).pathname);
  await page.getByLabel("Special details").fill("Trusted Taco Lunch. Fast-published tacos for $12.");
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
  const outreachOption = await page.locator('#outreach-restaurant option', { hasText: "Outreach Bistro" }).first().getAttribute("value");
  await page.locator("#outreach-restaurant").selectOption(outreachOption);
  await expect(page.locator("#outreach-submission-url")).toHaveValue(/\/submit\//);
  const submissionUrl = await page.locator("#outreach-submission-url").inputValue();
  await page.locator("#outreach-subject").fill("Browser outreach");
  await page.locator("#outreach-body").fill(`Use ${submissionUrl}\n\n--\nReply "no thanks" and I will stop emailing you.`);
  await page.getByRole("button", { name: "Send email" }).click();
  await expect(page.getByText(/outbound.*sent/i)).toBeVisible();

  const records = await capturedRecords(request);
  expect(records.some((record) => record.kind === "email" && record.to === "outreach@example.com")).toBeTruthy();
  expect(records.some((record) => record.kind === "loops_contact" && record.email === "outreach@example.com")).toBeTruthy();
  expect(records.some((record) => record.kind === "loops_event" && record.event_name === "founderOutreachSent")).toBeTruthy();
});
