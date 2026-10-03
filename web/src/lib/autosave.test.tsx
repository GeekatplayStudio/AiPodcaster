import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAutosave, type SaveState } from "./autosave";

function Probe({ value, baseline, save, onState }: { value: string; baseline?: string; save: (v: string) => Promise<unknown>; onState: (s: SaveState) => void }) {
  onState(useAutosave(value, save, { baseline, delay: 500 }));
  return null;
}

describe("useAutosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not save the server baseline, debounces edits and reports saved", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const states: SaveState[] = [];
    const { rerender } = render(<Probe value="a" baseline="a" save={save} onState={(s) => states.push(s)} />);
    await act(async () => vi.advanceTimersByTime(1000));
    expect(save).not.toHaveBeenCalled();

    rerender(<Probe value="ab" baseline="a" save={save} onState={(s) => states.push(s)} />);
    rerender(<Probe value="abc" baseline="a" save={save} onState={(s) => states.push(s)} />);
    await act(async () => vi.advanceTimersByTime(600));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
    expect(states.at(-1)).toBe("saved");
  });

  it("flushes a pending save on unmount and reports errors", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
    const states: SaveState[] = [];
    const { rerender, unmount } = render(<Probe value="x" baseline="x" save={save} onState={(s) => states.push(s)} />);
    rerender(<Probe value="y" baseline="x" save={save} onState={(s) => states.push(s)} />);
    await act(async () => vi.advanceTimersByTime(600));
    expect(states.at(-1)).toBe("error");

    rerender(<Probe value="z" baseline="x" save={save} onState={(s) => states.push(s)} />);
    unmount();
    expect(save).toHaveBeenLastCalledWith("z");
  });
});
