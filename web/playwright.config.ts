import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests drive the real UI against the real API with the deterministic
 * "fake" transcriber so no model download or GPU is needed.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 120_000,
  retries: 0,
  // The e2e stack uses its own ports (API 8010, web 5174) so it never collides with a running dev instance.
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8010",
      cwd: "../backend",
      url: "http://127.0.0.1:8010/healthz",
      reuseExistingServer: false,
      env: { AIPODCASTER_TRANSCRIBER: "fake", AIPODCASTER_DATA_DIR: "../backend/tests/.e2e-data", AIPODCASTER_ALLOWED_ORIGINS: "http://127.0.0.1:5174,http://localhost:5174" },
      timeout: 60_000,
    },
    {
      command: "npx vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      env: { AIPODCASTER_API_URL: "http://127.0.0.1:8010" },
      timeout: 60_000,
    },
  ],
});
