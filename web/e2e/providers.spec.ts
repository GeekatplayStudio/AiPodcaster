import { expect, test } from "@playwright/test";

test("provider settings: Ollama card, model test button and API key management", async ({ page }) => {
  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "Language model" })).toBeVisible();
  const providers = page.locator("#llm-provider");
  await expect(providers.locator("option")).toHaveCount(6);
  await providers.selectOption("ollama");
  await expect(page.getByTestId("ollama-card")).toBeVisible();
  await expect(page.getByText(/running|stopped|not installed/).first()).toBeVisible();

  await providers.selectOption("gemini");
  await expect(page.locator("#llm-model")).toHaveAttribute("placeholder", /gemini/);
  await providers.selectOption("none");

  await page.getByLabel("Speech provider").selectOption("custom_http");
  await expect(page.getByLabel("JSON body template")).toBeVisible();
  await page.getByLabel("Speech provider").selectOption("none");

  await page.getByLabel("Key label").fill("e2e client");
  await page.getByRole("button", { name: "Generate key" }).click();
  const shown = page.getByText(/New key \(shown once\)/);
  await expect(shown).toBeVisible();
  const key = (await shown.locator("code").innerText()).trim();
  expect(key).toMatch(/^apk_/);

  // The UI keeps working (same origin), while a keyless external request is rejected.
  const anonymous = await page.request.get("http://127.0.0.1:8010/v1/jobs", { headers: { Origin: "http://evil.example" } });
  expect(anonymous.status()).toBe(401);
  const authorised = await page.request.get("http://127.0.0.1:8010/v1/jobs", { headers: { "X-API-Key": key } });
  expect(authorised.status()).toBe(200);

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Revoke" }).first().click();
  await expect(page.getByRole("button", { name: "Revoke" })).toHaveCount(0);
  const open = await page.request.get("http://127.0.0.1:8010/v1/jobs", { headers: { Origin: "http://evil.example" } });
  expect(open.status()).toBe(200);
});
