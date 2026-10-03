import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProcessingJob, Project } from "../api/types";
import { ContinueCard } from "./ContinueCard";
import { ProjectPrompt } from "./ProjectPrompt";
import { rememberPlace } from "../lib/session";

const job = { id: "job-1", project_id: null, display_name: "Episode 2026-10-02 17:45", asset_name: "a.wav" } as unknown as ProcessingJob;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("ProjectPrompt", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("asks once, then shows a reminder banner after 'Not now'", () => {
    const { unmount } = render(<ProjectPrompt job={job} projects={[]} onJob={vi.fn()} onProjects={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: "Save this episode in a project" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("This episode is not in a project yet.")).toBeInTheDocument();
    unmount();
    render(<ProjectPrompt job={job} projects={[]} onJob={vi.fn()} onProjects={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("creates a project and files the episode", async () => {
    const created: Project = { id: "p-1", name: "Deep Focus", description: "", library_ids: [], linked_project_ids: [], online_fact_check: false, created_at: "", updated_at: "" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/v1/projects") && init?.method === "POST") return json(created, 201);
      if (url.endsWith("/v1/jobs/job-1/meta")) return json({ ...job, project_id: "p-1" });
      return json({}, 404);
    });
    const onJob = vi.fn();
    const onProjects = vi.fn();
    render(<ProjectPrompt job={job} projects={[]} onJob={onJob} onProjects={onProjects} />);
    fireEvent.change(screen.getByLabelText("Project (podcast or series) name"), { target: { value: "Deep Focus" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project and add episode" }));
    await waitFor(() => expect(onJob).toHaveBeenCalledWith(expect.objectContaining({ project_id: "p-1" })));
    expect(onProjects).toHaveBeenCalledWith([created]);
    const metaCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/meta"));
    expect(JSON.parse(String(metaCall?.[1]?.body))).toEqual({ project_id: "p-1" });
  });

  it("renders nothing once the episode has a project", () => {
    const { container } = render(<ProjectPrompt job={{ ...job, project_id: "p-9" }} projects={[]} onJob={vi.fn()} onProjects={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ContinueCard", () => {
  beforeEach(() => window.localStorage.clear());

  it("offers the last place and hides it for deleted episodes", () => {
    rememberPlace({ hash: "#/jobs/abc/stats", title: "Ep. 7", section: "stats" });
    const { unmount } = render(<ContinueCard existingIds={["abc"]} />);
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", "#/jobs/abc/stats");
    expect(screen.getByText(/Ep\. 7 · Statistics/)).toBeInTheDocument();
    unmount();
    const { container } = render(<ContinueCard existingIds={["other"]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
