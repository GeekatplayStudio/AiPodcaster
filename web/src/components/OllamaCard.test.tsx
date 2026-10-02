import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OllamaCard } from "./OllamaCard";

const status = {
  url: "http://127.0.0.1:11434",
  installed_binary: true,
  running: true,
  models: [{ name: "gemma3:12b", size_gb: 7.6, parameter_size: "12.2B", family: "gemma3", score: 88 }],
  recommended: "gemma3:12b",
  needs_pull: false,
  reason: "gemma3:12b is already installed and fits in 22 GB",
  budget_gb: 21.6,
  gpu_gb: 24,
  current_model: "gemma3:12b",
  current_loaded: true,
  pull: { model: "", status: "idle", completed: 0, total: 0, message: "" },
};

describe("OllamaCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows status, recommendation and installed models", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(status), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<OllamaCard currentModel="gemma3:12b" onModelChosen={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("running")).toBeInTheDocument());
    expect(screen.getByText(/already installed/)).toBeInTheDocument();
    expect(screen.getByText("gemma3:12b ✓")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare best model & use it" })).toBeEnabled();
  });

  it("offers to start Ollama when stopped", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ...status, running: false, models: [], recommended: "", reason: "Ollama is not running" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<OllamaCard currentModel="" onModelChosen={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Start Ollama" })).toBeInTheDocument());
  });
});
