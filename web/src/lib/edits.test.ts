import { describe, expect, it } from "vitest";
import type { EditProposal, TranscriptSegment } from "../api/types";
import { annotateSegment, mergeRanges, segmentDirty, setKind, summarise, toggleProposal, totalRemovedMs, validateFile } from "./edits";

const proposal = (over: Partial<EditProposal>): EditProposal => ({
  id: "p1",
  kind: "filler",
  start_ms: 0,
  end_ms: 300,
  text: "um",
  reason: "Verbal filler",
  confidence: 0.9,
  accepted: true,
  ...over,
});

const segment: TranscriptSegment = {
  id: 0,
  start_ms: 0,
  end_ms: 1100,
  text: "um hello world",
  words: [
    { text: "um", start_ms: 0, end_ms: 300, confidence: 1 },
    { text: "hello", start_ms: 400, end_ms: 700, confidence: 1 },
    { text: "world", start_ms: 800, end_ms: 1100, confidence: 1 },
  ],
};

describe("edits helpers", () => {
  it("annotates words covered by a proposal", () => {
    const views = annotateSegment(segment, [proposal({}), proposal({ id: "s", kind: "silence", start_ms: 0, end_ms: 2000 })]);
    expect(views[0].proposal?.id).toBe("p1");
    expect(views[1].proposal).toBeNull();
  });

  it("summarises and totals accepted edits without double counting overlaps", () => {
    const list = [proposal({}), proposal({ id: "p2", kind: "repeat", start_ms: 100, end_ms: 500 }), proposal({ id: "p3", kind: "profanity", accepted: false, start_ms: 900, end_ms: 1000 })];
    const summary = summarise(list);
    expect(summary.filler.total).toBe(1);
    expect(summary.profanity.accepted).toBe(0);
    expect(totalRemovedMs(list)).toBe(500);
  });

  it("merges ranges", () => {
    expect(mergeRanges([[5, 10], [0, 6], [20, 25], [24, 30], [40, 40]])).toEqual([
      [0, 10],
      [20, 30],
    ]);
  });

  it("toggles single proposals and whole kinds", () => {
    const list = [proposal({}), proposal({ id: "p2" })];
    expect(toggleProposal(list, "p1")[0].accepted).toBe(false);
    expect(toggleProposal(list, "p1", true)[0].accepted).toBe(true);
    expect(setKind(list, "filler", false).every((p) => !p.accepted)).toBe(true);
  });

  it("reports edited segments only", () => {
    const edited = [{ ...segment, text: "hello world" }];
    expect(segmentDirty([segment], edited)).toEqual([{ id: 0, text: "hello world" }]);
    expect(segmentDirty([segment], [segment])).toEqual([]);
  });

  it("validates files before upload", () => {
    const limit = 1024;
    expect(validateFile(new File(["x"], "a.wav"), limit)).toBeNull();
    expect(validateFile(new File(["x"], "a.txt"), limit)).toMatch(/Unsupported/);
    expect(validateFile(new File([], "a.mp3"), limit)).toMatch(/empty/);
    expect(validateFile(new File([new Uint8Array(2048)], "a.mp3"), limit)).toMatch(/larger/);
  });
});
