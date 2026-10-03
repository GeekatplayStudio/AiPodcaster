import { describe, expect, it } from "vitest";
import type { ApiInfo } from "../api/types";
import { friendlyDuration, isLongRecording, processingRange } from "./estimate";
import { forgetPlace, lastPlace, relativeTime, rememberPlace, saveScroll, savedScroll } from "./session";

const info = { estimates: { device: "gpu", analysis_rtf: 0.08, llm_seconds: 90, long_recording_seconds: 1800 } } as ApiInfo;

describe("estimates", () => {
  it("computes a processing range from the real-time factor", () => {
    const [low, high] = processingRange(3600, info);
    expect(low).toBeGreaterThan(200);
    expect(high).toBeGreaterThan(low);
    expect(processingRange(0, null)[0]).toBeGreaterThanOrEqual(10);
  });
  it("flags long or huge recordings", () => {
    expect(isLongRecording(1800, 10, info)).toBe(true);
    expect(isLongRecording(600, 2 * 1024 ** 3, info)).toBe(true);
    expect(isLongRecording(600, 50 * 1024 ** 2, info)).toBe(false);
  });
  it("formats friendly durations", () => {
    expect(friendlyDuration(30)).toBe("1 min");
    expect(friendlyDuration(45 * 60)).toBe("45 min");
    expect(friendlyDuration(2 * 3600 + 120)).toBe("2 h 2 min");
    expect(friendlyDuration(3 * 3600)).toBe("3 h");
  });
});

describe("session memory", () => {
  it("remembers and forgets the last place", () => {
    rememberPlace({ hash: "#/jobs/abc", title: "Ep. 1", section: "edit" });
    expect(lastPlace()).toMatchObject({ hash: "#/jobs/abc", title: "Ep. 1", section: "edit" });
    forgetPlace();
    expect(lastPlace()).toBeNull();
  });
  it("stores scroll positions per route", () => {
    saveScroll("#/settings", 420.6);
    expect(savedScroll("#/settings")).toBe(421);
    expect(savedScroll("#/unknown")).toBe(0);
  });
  it("describes relative time", () => {
    const now = Date.now();
    expect(relativeTime(now - 5 * 60_000, now)).toEqual({ value: 5, unit: "minute" });
    expect(relativeTime(now - 3 * 3_600_000, now)).toEqual({ value: 3, unit: "hour" });
    expect(relativeTime(now - 5 * 86_400_000, now)).toEqual({ value: 5, unit: "day" });
  });
});
