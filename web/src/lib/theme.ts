export type ThemeMode = "system" | "light" | "dark";
export type Accent = "blue" | "violet" | "teal" | "sunset" | "forest" | "mono";

export const ACCENTS: { id: Accent; label: string; swatch: string }[] = [
  { id: "blue", label: "Studio blue", swatch: "#1f6feb" },
  { id: "violet", label: "Violet", swatch: "#7c3aed" },
  { id: "teal", label: "Teal", swatch: "#0f9d8a" },
  { id: "sunset", label: "Sunset", swatch: "#e0592b" },
  { id: "forest", label: "Forest", swatch: "#2f8a3d" },
  { id: "mono", label: "Monochrome", swatch: "#444b5a" },
];

const MODE_KEY = "aipodcaster.theme";
const ACCENT_KEY = "aipodcaster.accent";

export interface ThemeState {
  mode: ThemeMode;
  accent: Accent;
}

export function loadTheme(): ThemeState {
  let mode: ThemeMode = "system";
  let accent: Accent = "blue";
  try {
    const storedMode = window.localStorage.getItem(MODE_KEY);
    if (storedMode === "light" || storedMode === "dark" || storedMode === "system") mode = storedMode;
    const storedAccent = window.localStorage.getItem(ACCENT_KEY);
    if (ACCENTS.some((a) => a.id === storedAccent)) accent = storedAccent as Accent;
  } catch {
    /* storage unavailable */
  }
  return { mode, accent };
}

export function applyTheme(state: ThemeState): void {
  const root = document.documentElement;
  if (state.mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", state.mode);
  root.setAttribute("data-accent", state.accent);
  try {
    window.localStorage.setItem(MODE_KEY, state.mode);
    window.localStorage.setItem(ACCENT_KEY, state.accent);
  } catch {
    /* storage unavailable */
  }
}

export function resolvedMode(mode: ThemeMode): "light" | "dark" {
  if (mode !== "system") return mode;
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
