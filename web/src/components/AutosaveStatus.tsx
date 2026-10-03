import { useTranslation } from "react-i18next";
import type { SaveState } from "../lib/autosave";

export function AutosaveStatus({ state }: { state: SaveState }) {
  const { t } = useTranslation();
  if (state === "idle") return null;
  const label = state === "saved" ? t("All changes saved") : state === "error" ? t("Could not save, retrying on next change") : t("Saving changes…");
  return (
    <span className={`autosave autosave-${state}`} role="status" aria-live="polite">
      <span aria-hidden="true">{state === "saved" ? "✓" : state === "error" ? "!" : "…"}</span> {label}
    </span>
  );
}
