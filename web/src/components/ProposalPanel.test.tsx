import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EditProposal } from "../api/types";
import { ProposalPanel } from "./ProposalPanel";

const proposals: EditProposal[] = [
  { id: "a", kind: "filler", start_ms: 1000, end_ms: 1300, text: "um", reason: "Verbal filler", confidence: 0.9, accepted: true },
  { id: "b", kind: "silence", start_ms: 5000, end_ms: 7000, text: "", reason: "Long pause", confidence: 0.8, accepted: false },
];

describe("ProposalPanel", () => {
  it("renders counts and forwards toggles", () => {
    const onToggle = vi.fn();
    const onKind = vi.fn();
    const onPreview = vi.fn();
    render(<ProposalPanel proposals={proposals} onToggle={onToggle} onKind={onKind} onPreview={onPreview} />);
    expect(screen.getByText("of 2 edits accepted").previousSibling).toHaveTextContent("1");
    expect(screen.getByText("300 ms")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Pause at 00:05"));
    expect(onToggle).toHaveBeenCalledWith("b", true);
    fireEvent.click(screen.getAllByText("None")[0]);
    expect(onKind).toHaveBeenCalledWith("filler", false);
    fireEvent.click(screen.getAllByTitle("Listen in context")[0]);
    expect(onPreview).toHaveBeenCalled();
  });

  it("disables controls when read only", () => {
    render(<ProposalPanel proposals={proposals} readOnly onToggle={vi.fn()} onKind={vi.fn()} onPreview={vi.fn()} />);
    expect(screen.getByLabelText("Filler at 00:01")).toBeDisabled();
    expect(screen.queryByText("None")).toBeNull();
  });
});
