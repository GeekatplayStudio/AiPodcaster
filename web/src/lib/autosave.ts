import { useEffect, useRef, useState } from "react";

export type SaveState = "idle" | "pending" | "saving" | "saved" | "error";

interface Options {
  /** Server version of the value; nothing is saved while the value equals it. */
  baseline?: unknown;
  enabled?: boolean;
  delay?: number;
}

/**
 * Debounced autosave. Saves `value` shortly after it stops changing, flushes a pending
 * save when the component unmounts (navigation) and warns before closing the tab while
 * a save is outstanding.
 */
export function useAutosave<T>(value: T, save: (value: T) => Promise<unknown>, { baseline, enabled = true, delay = 800 }: Options = {}): SaveState {
  const [state, setState] = useState<SaveState>("idle");
  const serialized = JSON.stringify(value);
  const baselineSerialized = baseline === undefined ? undefined : JSON.stringify(baseline);
  const saveRef = useRef(save);
  const pendingRef = useRef<string | null>(null);

  useEffect(() => {
    saveRef.current = save;
  });

  useEffect(() => {
    if (!enabled || serialized === baselineSerialized) {
      pendingRef.current = null;
      return;
    }
    pendingRef.current = serialized;
    const mark = window.setTimeout(() => setState("pending"), 0);
    const timer = window.setTimeout(async () => {
      pendingRef.current = null;
      setState("saving");
      try {
        await saveRef.current(JSON.parse(serialized) as T);
        setState("saved");
      } catch {
        setState("error");
      }
    }, delay);
    return () => {
      window.clearTimeout(mark);
      window.clearTimeout(timer);
    };
  }, [serialized, baselineSerialized, enabled, delay]);

  // Flush on unmount so navigating away within the debounce window loses nothing.
  useEffect(
    () => () => {
      if (pendingRef.current !== null) void saveRef.current(JSON.parse(pendingRef.current) as T).catch(() => undefined);
    },
    [],
  );

  useEffect(() => {
    if (state !== "pending" && state !== "saving") return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  return state;
}

/** Current time that re-renders every `intervalMs` (for countdowns). */
export function useNow(intervalMs = 1000, active = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs, active]);
  return now;
}
