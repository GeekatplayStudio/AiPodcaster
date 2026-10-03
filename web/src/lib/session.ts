/** Remembers where the user was so the app can offer "continue where you left off". */
const PLACE_KEY = "aipodcaster.lastPlace";
const SCROLL_KEY = "aipodcaster.scroll";

export interface Place {
  hash: string;
  title: string;
  section: "edit" | "stats" | "publish";
  at: number;
}

function read<T>(storage: Storage | undefined, key: string): T | null {
  try {
    const raw = storage?.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(storage: Storage | undefined, key: string, value: unknown): void {
  try {
    storage?.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
}

const local = () => (typeof window === "undefined" ? undefined : window.localStorage);
const session = () => (typeof window === "undefined" ? undefined : window.sessionStorage);

export function rememberPlace(place: Omit<Place, "at">): void {
  write(local(), PLACE_KEY, { ...place, at: Date.now() });
}

export function lastPlace(): Place | null {
  return read<Place>(local(), PLACE_KEY);
}

export function forgetPlace(): void {
  try {
    local()?.removeItem(PLACE_KEY);
  } catch {
    /* ignore */
  }
}

export function saveScroll(hash: string, y: number): void {
  const map = read<Record<string, number>>(session(), SCROLL_KEY) ?? {};
  map[hash || "#/"] = Math.max(0, Math.round(y));
  write(session(), SCROLL_KEY, map);
}

export function savedScroll(hash: string): number {
  return read<Record<string, number>>(session(), SCROLL_KEY)?.[hash || "#/"] ?? 0;
}

/** Restore a scroll position once the (asynchronously loaded) page is tall enough. */
export function restoreScroll(hash: string): void {
  const target = savedScroll(hash);
  if (!target) {
    window.scrollTo({ top: 0 });
    return;
  }
  const started = Date.now();
  const attempt = () => {
    if (document.documentElement.scrollHeight - window.innerHeight >= target || Date.now() - started > 2000) {
      window.scrollTo({ top: target });
      return;
    }
    window.requestAnimationFrame(attempt);
  };
  window.requestAnimationFrame(attempt);
}

export function relativeTime(at: number, now = Date.now()): { value: number; unit: "minute" | "hour" | "day" } {
  const minutes = Math.max(1, Math.round((now - at) / 60_000));
  if (minutes < 60) return { value: minutes, unit: "minute" };
  const hours = Math.round(minutes / 60);
  if (hours < 48) return { value: hours, unit: "hour" };
  return { value: Math.round(hours / 24), unit: "day" };
}
