import { expect, test } from "@playwright/test";

const RUSSIAN = `ВЕДУЩИЙ: Ээ, привет всем, добро пожаловать в наш подкаст.
ГОСТЬ: Ммм, спасибо. Сегодня мы, как бы, поговорим о привычках и внимании.
ВЕДУЩИЙ: Нууу, давайте начнём с самого простого примера из жизни.`;

test("unnamed episode → project prompt → autosave survives reload → continue where you left off", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Transcript / text" }).click();
  await page.getByLabel(/or paste text/).fill(RUSSIAN);
  await expect(page.getByText(/looks like speaker dialogue/)).toBeVisible();
  await page.getByRole("button", { name: "Create episode from text" }).click();

  // No name given: the episode is named after the date and time.
  const heading = page.getByRole("heading", { name: /^Episode \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/, level: 1 });
  await expect(heading).toBeVisible();
  const episodeName = (await heading.innerText()).trim();

  // Russian is detected and Russian hesitations are flagged.
  await expect(page.getByLabel("Spoken language")).toContainText("Auto-detected: Russian");
  await expect(page.getByText("“Ээ,”")).toBeVisible();
  await expect(page.getByText("“Нууу,”")).toBeVisible();

  // Project prompt: create a project straight from the episode.
  const dialog = page.getByRole("dialog", { name: "Save this episode in a project" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Project (podcast or series) name").fill("Привычки и фокус");
  await dialog.getByRole("button", { name: "Create project and add episode" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText(/· Привычки и фокус/)).toBeVisible();

  // Autosave: toggle a suggestion and change the title, then reload.
  const decisions = page.getByRole("checkbox", { name: /^\S+ at \d\d:\d\d$/ });
  const firstDecision = decisions.first();
  const before = await firstDecision.isChecked();
  await firstDecision.click();
  await page.getByLabel("Episode title").fill("Привычки — выпуск 1");
  await expect(page.getByRole("status").filter({ hasText: "All changes saved" })).toBeVisible({ timeout: 10_000 });
  // The generated date name gives way to the chosen title.
  await expect(page.getByRole("heading", { name: "Привычки — выпуск 1", level: 1 })).toBeVisible();
  await page.reload();
  await expect(decisions.first()).toBeChecked({ checked: !before });
  await expect(page.getByLabel("Episode title")).toHaveValue("Привычки — выпуск 1");

  // Continue where you left off.
  await page.goto("/#/");
  const continueCard = page.getByRole("region", { name: "Continue where you left off" });
  await expect(continueCard).toContainText("Привычки — выпуск 1");
  await continueCard.getByRole("link", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Привычки — выпуск 1", level: 1 })).toBeVisible();
  expect(episodeName).toMatch(/^Episode /);
});

test("interface language switch is remembered", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Interface language").selectOption("ru");
  await expect(page.getByRole("button", { name: "Выпуски" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
  await page.reload();
  await expect(page.getByRole("button", { name: "Настройки" })).toBeVisible();
  await page.getByLabel("Язык интерфейса").selectOption("en");
  await expect(page.getByRole("button", { name: "Episodes" })).toBeVisible();
});

test("text import keeps an unsent draft", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Transcript / text" }).click();
  await page.getByLabel(/or paste text/).fill("Draft that should survive a reload of the page.");
  await page.waitForTimeout(600);
  await page.reload();
  await expect(page.getByLabel(/or paste text/)).toHaveValue("Draft that should survive a reload of the page.");
  await page.getByLabel(/or paste text/).fill("");
});
