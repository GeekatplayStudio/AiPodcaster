import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const FACTS = [
  "# Habits research notes",
  "",
  "Building better habits takes on average 66 days according to a 2009 study by Phillippa Lally at University College London.",
  "",
  "Habit stacking, described by James Clear in Atomic Habits (2018), pairs a new habit with an existing routine.",
  "",
].join("\n");

function fixtures(): { wav: string; md: string } {
  const dir = mkdtempSync(join(tmpdir(), "aipodcaster-factcheck-"));
  const wav = join(dir, "habits.wav");
  execFileSync("ffmpeg", ["-y", "-v", "error", "-f", "lavfi", "-i", "aevalsrc=sin(440*2*PI*t)*0.4*lt(mod(t\\,8)\\,5):s=16000:d=12", "-c:a", "pcm_s16le", wav]);
  const md = join(dir, "facts.md");
  writeFileSync(md, FACTS, "utf-8");
  return { wav, md };
}

test("library → project → episode fact check", async ({ page }) => {
  const { wav, md } = fixtures();
  const suffix = Date.now().toString(36);

  await page.goto("/#/libraries");
  await page.getByLabel("Name").fill(`Habits ${suffix}`);
  await page.getByRole("button", { name: "Create library" }).click();
  await expect(page.getByRole("heading", { name: `Habits ${suffix}` })).toBeVisible();
  await page.getByLabel("Add documents").setInputFiles(md);
  await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 90_000 });
  await page.getByLabel("Test a search").fill("how long to form a habit");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/66 days/).first()).toBeVisible();

  await page.goto("/#/projects");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill(`Habits show ${suffix}`);
  await page.getByLabel(`Habits ${suffix}`, { exact: false }).check();
  await page.getByRole("button", { name: "Save project" }).click();
  await expect(page.getByText(`Habits show ${suffix}`)).toBeVisible();

  await page.goto("/#/");
  await page.getByLabel("Project for new uploads").selectOption({ label: `Habits show ${suffix}` });
  await page.getByLabel("Choose a recording").setInputFiles(wav);
  await expect(page.getByRole("heading", { name: "Suggested edits" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue(/.+/);
  await page.getByRole("button", { name: "Run fact check" }).click();
  await expect(page.getByText(/claims checked/)).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/judge: heuristic/)).toBeVisible();
});
