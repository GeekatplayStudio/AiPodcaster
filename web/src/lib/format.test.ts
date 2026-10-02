import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatTime, isProcessing, stepIndex } from "./format";

describe("format helpers", () => {
  it("formats times", () => {
    expect(formatTime(0)).toBe("00:00");
    expect(formatTime(61_500)).toBe("01:01");
    expect(formatTime(3_661_000)).toBe("1:01:01");
  });
  it("formats durations", () => {
    expect(formatDuration(250)).toBe("250 ms");
    expect(formatDuration(2_500)).toBe("2.5 s");
    expect(formatDuration(90_000)).toBe("01:30");
  });
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(50 * 1024 * 1024)).toBe("50 MB");
  });
  it("knows which stages are processing", () => {
    expect(isProcessing("transcribe")).toBe(true);
    expect(isProcessing("waiting_for_approval")).toBe(false);
    expect(stepIndex("complete")).toBe(4);
    expect(stepIndex("failed")).toBe(0);
  });
});
