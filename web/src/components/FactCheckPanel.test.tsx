import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FactCheck, ProcessingJob } from "../api/types";
import { FactCheckPanel, sortChecks } from "./FactCheckPanel";

const check = (over: Partial<FactCheck>): FactCheck => ({
  id: "c",
  segment_id: 0,
  start_ms: 0,
  claim: "claim",
  verdict: "supported",
  flagged: false,
  confidence: 0.7,
  explanation: "",
  suggested_correction: "",
  evidence: [],
  dismissed: false,
  ...over,
});

describe("sortChecks", () => {
  it("puts open flags first, then uncertain, then the rest by time", () => {
    const sorted = sortChecks([
      check({ id: "a", start_ms: 1000 }),
      check({ id: "b", verdict: "uncertain", start_ms: 500 }),
      check({ id: "c", verdict: "contradicted", flagged: true, start_ms: 9000 }),
      check({ id: "d", verdict: "contradicted", flagged: true, dismissed: true, start_ms: 100 }),
    ]);
    expect(sorted.map((c) => c.id)).toEqual(["c", "b", "d", "a"]);
  });
});

describe("FactCheckPanel", () => {
  it("renders a completed report with flagged claim and evidence", () => {
    const job = {
      id: "j",
      project_id: "p",
      verification: {
        status: "complete",
        message: "",
        error: null,
        used_libraries: ["Habits"],
        used_online: false,
        judge: "heuristic (claims: heuristic)",
        claims_checked: 2,
        flagged: 1,
        checks: [
          check({ id: "x", claim: "Habits take 21 days", verdict: "contradicted", flagged: true, start_ms: 65_000, explanation: "Different figures", evidence: [{ source_kind: "library", source: "Habits / facts.md", url: null, excerpt: "66 days", score: 0.8, library_id: "l", document_id: "d" }] }),
          check({ id: "y", claim: "fine", verdict: "supported" }),
        ],
        finished_at: null,
      },
    } as unknown as ProcessingJob;
    const project = { id: "p", name: "Show", description: "", library_ids: ["l"], linked_project_ids: [], online_fact_check: false, created_at: "", updated_at: "" };
    render(<FactCheckPanel job={job} project={project} projects={[project]} onJob={vi.fn()} onSeek={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByText("1 flagged")).toBeInTheDocument();
    expect(screen.getByText(/Habits take 21 days/)).toBeInTheDocument();
    expect(screen.queryByText(/“fine”/)).toBeNull();
    expect(screen.getByRole("button", { name: "Run fact check again" })).toBeEnabled();
    expect(screen.getByText(/Heuristic mode/)).toBeInTheDocument();
  });

  it("disables running when there is no project and online is off", () => {
    const job = { id: "j", project_id: null, verification: { status: "not_run", message: "", error: null, used_libraries: [], used_online: false, judge: "", claims_checked: 0, flagged: 0, checks: [], finished_at: null } } as unknown as ProcessingJob;
    render(<FactCheckPanel job={job} project={null} projects={[]} onJob={vi.fn()} onSeek={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Run fact check" })).toBeDisabled();
  });
});
