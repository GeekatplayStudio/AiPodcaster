import { describe, expect, it } from "vitest";
import type { JobSummary } from "../api/types";
import { DEFAULT_FILTERS, filterEpisodes, groupByProject, moveItem } from "./episodes";

const item = (over: Partial<JobSummary>): JobSummary => ({
  id: "a",
  project_id: null,
  asset_name: "a.wav",
  display_name: "Alpha",
  source_kind: "audio",
  archived: false,
  order: 0,
  tags: [],
  stage: "complete",
  progress: 100,
  message: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  duration_ms: 1000,
  final_duration_ms: 900,
  word_count: 10,
  proposal_count: 0,
  accepted_edits: 0,
  flagged_claims: 0,
  output_count: 0,
  published: 0,
  language: "en",
  ...over,
});

const items = [
  item({ id: "a", display_name: "Alpha", order: 2, word_count: 10 }),
  item({ id: "b", display_name: "Beta", order: 1, source_kind: "text", tags: ["habits"], stage: "waiting_for_approval", project_id: "p1", flagged_claims: 2, word_count: 50 }),
  item({ id: "c", display_name: "Gamma", order: 0, archived: true, project_id: "p1" }),
];

describe("episode filters", () => {
  it("hides archived by default and respects manual order", () => {
    expect(filterEpisodes(items, DEFAULT_FILTERS).map((i) => i.id)).toEqual(["b", "a"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, showArchived: true }).map((i) => i.id)).toEqual(["c", "b", "a"]);
  });
  it("filters by text, source, project, stage and flags", () => {
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, query: "HABITS" }).map((i) => i.id)).toEqual(["b"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, source: "text" }).map((i) => i.id)).toEqual(["b"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, projectId: "none" }).map((i) => i.id)).toEqual(["a"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, stage: "needs_review" }).map((i) => i.id)).toEqual(["b"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, flaggedOnly: true }).map((i) => i.id)).toEqual(["b"]);
  });
  it("sorts by name and words", () => {
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, sort: "name" }).map((i) => i.id)).toEqual(["a", "b"]);
    expect(filterEpisodes(items, { ...DEFAULT_FILTERS, sort: "words" }).map((i) => i.id)).toEqual(["b", "a"]);
  });
  it("groups by project and moves items", () => {
    const groups = groupByProject(items, (id) => (id === "p1" ? "Show" : "?"));
    expect(groups.map((g) => [g.title, g.items.length])).toEqual([
      ["No project", 1],
      ["Show", 2],
    ]);
    expect(moveItem([1, 2, 3], 0, 2)).toEqual([2, 3, 1]);
    expect(moveItem([1, 2, 3], 5, 0)).toEqual([1, 2, 3]);
  });
});
