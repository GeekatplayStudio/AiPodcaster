import { expect, test } from "@playwright/test";

const TRANSCRIPT = `HOST: Welcome back to the focus show, everyone.
GUEST: Thanks for having me. Um, I think it takes about 23 minutes to refocus after an interruption.
HOST: That is a big number. Let's talk about deep work habits for remote teams and how to protect attention.
GUEST: Absolutely, absolutely. The the first step is a calendar block every morning.`;

test("text import → library management → stats → publish page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Transcript / text" }).click();
  await page.getByLabel(/or paste text/).fill(TRANSCRIPT);
  await expect(page.getByText(/looks like speaker dialogue/)).toBeVisible();
  await page.getByLabel("Episode name").fill("Focus interview");
  await page.getByRole("button", { name: "Create episode from text" }).click();

  await expect(page.getByRole("heading", { name: "Focus interview" })).toBeVisible();
  await page.getByRole("button", { name: "Not now" }).click();
  await expect(page.getByText(/Text episode: timing is estimated/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Suggested edits" })).toBeVisible();
  await expect(page.getByLabel("Voice")).toBeDisabled();

  await page.getByRole("link", { name: "Statistics" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("words spoken").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Speaking pace per minute" })).toBeVisible();
  await expect(page.locator("rect.bar").first()).toBeVisible();

  await page.getByRole("link", { name: "Publish & export" }).click();
  await page.getByRole("button", { name: "Generate with AI" }).click();
  await expect(page.locator("#kit-title-input")).toHaveValue(/Focus/i, { timeout: 30_000 });
  await expect(page.getByLabel("Hashtags")).toHaveValue(/#/);
  await page.getByRole("button", { name: "Generate artwork" }).click();
  await expect(page.getByAltText("Episode thumbnail")).toBeVisible({ timeout: 30_000 });

  await page.goto("/#/");
  await page.getByLabel("Search episodes").fill("focus");
  await expect(page.getByRole("link", { name: "Focus interview" })).toBeVisible();
  await page.getByRole("button", { name: "Rename Focus interview" }).click();
  const rename = page.getByRole("table").getByLabel("Episode name");
  await rename.fill("Focus interview v2");
  await rename.press("Enter");
  await expect(page.getByRole("link", { name: "Focus interview v2" })).toBeVisible();
  await page.getByLabel("Select Focus interview v2").check();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(page.getByRole("link", { name: "Focus interview v2" })).toHaveCount(0);
  await page.getByLabel("Show archived").check();
  await expect(page.getByRole("link", { name: "Focus interview v2" })).toBeVisible();
});

test("theme menu switches mode and accent", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Theme" }).click();
  await page.getByRole("button", { name: "dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Sunset" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "sunset");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "sunset");
});
