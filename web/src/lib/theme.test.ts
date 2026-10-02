import { describe, expect, it } from "vitest";
import { applyTheme, loadTheme } from "./theme";
import { detectPastedFormat } from "../components/TextImportPanel";

describe("theme", () => {
  it("applies and persists mode and accent", () => {
    applyTheme({ mode: "dark", accent: "teal" });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-accent")).toBe("teal");
    expect(loadTheme()).toEqual({ mode: "dark", accent: "teal" });
    applyTheme({ mode: "system", accent: "blue" });
    expect(document.documentElement.getAttribute("data-theme")).toBeNull();
  });
});

describe("pasted text detection", () => {
  it("recognises captions, timestamps, dialogue and prose", () => {
    expect(detectPastedFormat("WEBVTT\n\n00:00.000 --> 00:01.000\nHi")).toBe("WebVTT captions");
    expect(detectPastedFormat("1\n00:00:01,000 --> 00:00:02,000\nHi")).toBe("SRT captions");
    expect(detectPastedFormat("[00:01] hello there\n[00:05] second line\n[00:09] third")).toBe("timestamped transcript");
    expect(detectPastedFormat("HOST: hi\nGUEST: hello\nHOST: ok")).toBe("speaker dialogue");
    expect(detectPastedFormat("Just a plain paragraph of text.")).toBe("plain text / script");
  });
});
