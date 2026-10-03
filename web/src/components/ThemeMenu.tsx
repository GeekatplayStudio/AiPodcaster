import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ACCENTS, applyTheme, loadTheme, type ThemeMode, type ThemeState } from "../lib/theme";

export function ThemeMenu() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState<ThemeState>(() => loadTheme());
  const [open, setOpen] = useState(false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <div className="theme-menu">
      <button type="button" className="btn sm" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((v) => !v)} title={t("Theme")}>
        <span className="swatch" style={{ background: ACCENTS.find((a) => a.id === theme.accent)?.swatch }} aria-hidden="true" /> {t("Theme")}
      </button>
      {open && (
        <div className="theme-popover" role="dialog" aria-label={t("Theme settings")}>
          <strong className="small">{t("Mode")}</strong>
          <div className="btn-row" style={{ marginBottom: 10 }}>
            {(["system", "light", "dark"] as ThemeMode[]).map((mode) => (
              <button key={mode} type="button" className={`btn sm${theme.mode === mode ? " primary" : ""}`} onClick={() => setTheme({ ...theme, mode })} aria-pressed={theme.mode === mode}>
                {t(mode)}
              </button>
            ))}
          </div>
          <strong className="small">{t("Accent")}</strong>
          <div className="accent-grid">
            {ACCENTS.map((accent) => (
              <button key={accent.id} type="button" className={`accent-choice${theme.accent === accent.id ? " active" : ""}`} onClick={() => setTheme({ ...theme, accent: accent.id })} aria-pressed={theme.accent === accent.id} title={t(accent.label)}>
                <span className="swatch" style={{ background: accent.swatch }} aria-hidden="true" />
                <span>{t(accent.label)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
