import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

function makeSample(): string {
  const dir = mkdtempSync(join(tmpdir(), "aipodcaster-e2e-"));
  const path = join(dir, "episode.wav");
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", "aevalsrc=sin(440*2*PI*t)*0.4*lt(mod(t\\,8)\\,5):s=16000:d=12", "-c:a", "pcm_s16le", path]);
  return path;
}

test("upload, review, approve and download an episode", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText(/API online/);

  await page.getByLabel("Choose a recording").setInputFiles(makeSample());
  await expect(page.getByRole("heading", { name: "episode.wav" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Suggested edits" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/edits accepted/)).toBeVisible();

  // Reject one proposal via its checkbox and edit the first segment's text.
  const first = page.getByRole("checkbox").first();
  await first.uncheck();
  await page.getByRole("button", { name: /^Edit text at/ }).first().click();
  await page.getByLabel(/Edit transcript at/).fill("Welcome back to the programme.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Welcome back to the programme.")).toBeVisible();

  await page.getByLabel("Episode title").fill("E2E Episode");
  await page.getByRole("button", { name: "Approve transcript & produce episode" }).click();
  await expect(page.getByRole("heading", { name: "Episode ready" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("Episode (MP3)")).toBeVisible();
  await expect(page.getByText("Publish kit (zip)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "E2E Episode" })).toBeVisible();

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Download" }).first().click()]);
  expect(download.suggestedFilename()).toMatch(/\.mp3$/);

  await page.getByRole("button", { name: "← Episodes" }).click();
  await expect(page.getByRole("link", { name: "E2E Episode" }).first()).toBeVisible();
});

test("settings round-trip masks secrets", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByLabel("OpenAI API key").fill("sk-e2e-secret");
  await page.getByLabel("Pause longer than (ms)").fill("2000");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText(/Settings saved/)).toBeVisible();
  await expect(page.getByLabel("OpenAI API key")).toHaveValue("••••••••");
  await page.reload();
  await expect(page.getByLabel("Pause longer than (ms)")).toHaveValue("2000");
  await page.getByLabel("OpenAI API key").fill("");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText(/Settings saved/)).toBeVisible();
});
