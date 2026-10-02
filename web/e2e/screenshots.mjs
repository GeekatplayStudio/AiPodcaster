// Captures README screenshots against a running stack (API 8000, web 5173).
// Usage: node e2e/screenshots.mjs [outputDir]
// Seeds a demo episode, library and project, shoots every screen, then removes the demo data.
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const API = process.env.AIPODCASTER_URL ?? "http://127.0.0.1:8000";
const WEB = process.env.AIPODCASTER_WEB ?? "http://localhost:5173";
const OUT = resolve(process.argv[2] ?? "../docs/screenshots");
const AUDIO = process.env.DEMO_AUDIO;
mkdirSync(OUT, { recursive: true });

const FACTS = `# Focus research notes

Gloria Mark and colleagues at the University of California, Irvine reported in 2008 that it takes about 23 minutes and 15 seconds to return to a task after an interruption.

Cal Newport describes a protected deep work block of 90 minutes as the most effective unit of concentrated effort.

Checking messages in two or three batches per day reduces context switching compared with continuous monitoring.
`;

async function api(method, path, body, isForm = false) {
  const response = await fetch(`${API}${path}`, { method, headers: isForm ? {} : { "Content-Type": "application/json" }, body: isForm ? body : body ? JSON.stringify(body) : undefined });
  if (!response.ok) throw new Error(`${method} ${path} -> ${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
}

async function waitJob(id, stages, timeout = 900_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const job = await api("GET", `/v1/jobs/${id}`);
    if (stages.includes(job.stage)) return job;
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error(`timeout waiting for ${stages}`);
}

async function waitVerification(id, timeout = 900_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const job = await api("GET", `/v1/jobs/${id}`);
    if (["complete", "failed"].includes(job.verification.status)) return job;
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error("timeout waiting for verification");
}

async function seed() {
  const library = await api("POST", "/v1/libraries", { name: "Focus research", description: "Papers and notes behind the Deep Focus show" });
  const form = new FormData();
  form.append("files", new Blob([FACTS], { type: "text/markdown" }), "focus-research.md");
  await api("POST", `/v1/libraries/${library.id}/documents`, form, true);
  const project = await api("POST", "/v1/projects", { name: "Deep Focus", description: "Weekly show about attention and habits", library_ids: [library.id], linked_project_ids: [], online_fact_check: false });
  const spinoff = await api("POST", "/v1/projects", { name: "Deep Focus Shorts", description: "Short clips reusing the main research", library_ids: [], linked_project_ids: [project.id], online_fact_check: false });

  let job;
  if (AUDIO) {
    const { readFileSync } = await import("node:fs");
    const audioForm = new FormData();
    audioForm.append("file", new Blob([readFileSync(AUDIO)], { type: "audio/wav" }), "deep-focus-ep14-raw.wav");
    audioForm.append("project_id", project.id);
    job = await api("POST", "/v1/jobs", audioForm, true);
    job = await waitJob(job.id, ["waiting_for_approval", "failed"]);
  } else {
    job = await api("POST", "/v1/jobs/text", { text: FACTS, name: "deep-focus-ep14.txt", project_id: project.id, words_per_minute: 150 });
  }
  await api("PATCH", `/v1/jobs/${job.id}/meta`, { display_name: "Ep. 14 — Interruptions and deep work", tags: ["focus", "habits", "season-2"] });
  for (let i = 0; i < 25; i++) {
    const lib = await api("GET", `/v1/libraries/${library.id}`);
    if (lib.documents.every((d) => d.status === "ready")) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  await api("POST", `/v1/jobs/${job.id}/verify`, { use_libraries: true, use_online: false });
  await waitVerification(job.id);

  const text = await api("POST", "/v1/jobs/text", { text: "HOST: Welcome to the shorts feed.\nGUEST: Today in two minutes: why batching your inbox beats constant checking.\nHOST: Research suggests two or three windows a day is enough for most teams.", name: "shorts-inbox-batching.txt", project_id: spinoff.id, words_per_minute: 160 });
  await api("PATCH", `/v1/jobs/${text.id}/meta`, { display_name: "Short — Inbox batching", tags: ["shorts"] });

  const decisions = job.proposals.map((p) => ({ id: p.id, accepted: p.kind !== "filler" || p.confidence > 0.8 }));
  await api("POST", `/v1/jobs/${job.id}/approval`, { decisions, segments: [], voice_mode: "original", title: "Interruptions and deep work" });
  await waitJob(job.id, ["complete", "failed"]);
  await api("POST", `/v1/jobs/${job.id}/kit/generate`);
  await api("POST", `/v1/jobs/${job.id}/kit/thumbnail`, { prompt: "", size: "square" });
  const targets = [
    await api("POST", "/v1/publish/targets", { name: "geekatplay.com", kind: "generic_webhook", config: { url: "https://www.geekatplay.com/aipodcaster-receiver.php", secret: "demo-secret" }, enabled: true }),
    await api("POST", "/v1/publish/targets", { name: "Spotify for Creators", kind: "spotify_for_creators", config: {}, enabled: true }),
    await api("POST", "/v1/publish/targets", { name: "YouTube channel", kind: "youtube", config: {}, enabled: true }),
  ];
  await api("POST", `/v1/jobs/${job.id}/publish`, { target_id: targets[1].id });
  return { library, project, spinoff, job, text, targets };
}

async function shoot(seeded) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme: "light" });
  const page = await context.newPage();
  await page.addInitScript(() => {
    localStorage.setItem("aipodcaster.theme", "light");
    localStorage.setItem("aipodcaster.accent", "blue");
    localStorage.setItem("aipodcaster.episodeFilters", JSON.stringify({ query: "", stage: "all", source: "all", projectId: "all", showArchived: false, flaggedOnly: false, sort: "manual", groupByProject: false }));
  });
  const snap = async (name, hash, options = {}) => {
    await page.goto(`${WEB}/${hash}`);
    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(options.wait ?? 800);
    if (options.prepare) await options.prepare();
    await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: options.fullPage ?? false });
    console.log("captured", name);
  };

  await snap("01-episodes", "#/", { prepare: async () => page.getByRole("button", { name: "Hide import" }).click().catch(() => undefined) });
  await snap("02-import", "#/", { prepare: async () => page.getByRole("tab", { name: "Transcript / text" }).click() });
  await snap("03-review", `#/jobs/${seeded.job.id}`, { wait: 1500 });
  await snap("04-fact-check", `#/jobs/${seeded.job.id}`, {
    wait: 1500,
    prepare: async () => {
      await page.getByRole("button", { name: /Show all/ }).click().catch(() => undefined);
      await page.getByRole("heading", { name: "Fact check" }).scrollIntoViewIfNeeded();
    },
  });
  await snap("05-stats", `#/jobs/${seeded.job.id}/stats`, { wait: 1200, fullPage: true });
  await snap("06-publish", `#/jobs/${seeded.job.id}/publish`, { wait: 1500, fullPage: true });
  await snap("07-libraries", "#/libraries", { prepare: async () => page.getByRole("button", { name: "Open" }).first().click().then(() => page.waitForTimeout(600)) });
  await snap("08-projects", "#/projects", { prepare: async () => page.getByRole("button", { name: "Edit" }).last().click().then(() => page.waitForTimeout(300)) });
  await snap("09-settings", "#/settings", {
    wait: 1500,
    prepare: async () => {
      await page.locator("#llm-provider").selectOption("ollama");
      await page.waitForTimeout(1500);
    },
  });

  // Dark hero
  await page.addInitScript(() => {
    localStorage.setItem("aipodcaster.theme", "dark");
    localStorage.setItem("aipodcaster.accent", "violet");
  });
  await page.goto(`${WEB}/#/jobs/${seeded.job.id}`);
  await page.evaluate(() => {
    localStorage.setItem("aipodcaster.theme", "dark");
    localStorage.setItem("aipodcaster.accent", "violet");
  });
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  await page.getByRole("heading", { name: "Transcript" }).evaluate((el) => el.closest("section")?.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: join(OUT, "00-hero-dark.png") });
  console.log("captured 00-hero-dark");
  await browser.close();
}

async function cleanup(seeded) {
  for (const target of seeded.targets) await api("DELETE", `/v1/publish/targets/${target.id}`).catch(() => undefined);
  await api("DELETE", `/v1/jobs/${seeded.text.id}`).catch(() => undefined);
  await api("DELETE", `/v1/jobs/${seeded.job.id}`).catch(() => undefined);
  await api("DELETE", `/v1/projects/${seeded.spinoff.id}`).catch(() => undefined);
  await api("DELETE", `/v1/projects/${seeded.project.id}`).catch(() => undefined);
  await api("DELETE", `/v1/libraries/${seeded.library.id}`).catch(() => undefined);
}

const seeded = await seed();
writeFileSync(join(tmpdir(), "aipodcaster-seed.json"), JSON.stringify(seeded, null, 2));
try {
  await shoot(seeded);
} finally {
  if (!process.env.KEEP_DEMO) await cleanup(seeded);
}
console.log("done ->", OUT);
