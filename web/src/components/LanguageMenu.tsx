import { useTranslation } from "react-i18next";
import { UI_LANGUAGES } from "../i18n";

/** Interface language picker; the choice is stored in this browser. */
export function LanguageMenu() {
  const { t, i18n } = useTranslation();
  const current = UI_LANGUAGES.some((language) => language.code === i18n.resolvedLanguage) ? i18n.resolvedLanguage : "en";
  return (
    <label className="language-menu" title={t("Interface language")}>
      <span className="sr-only">{t("Interface language")}</span>
      <span aria-hidden="true">🌐</span>
      <select value={current} onChange={(event) => void i18n.changeLanguage(event.target.value)} aria-label={t("Interface language")}>
        {UI_LANGUAGES.map((language) => (
          <option key={language.code} value={language.code}>
            {language.label}
          </option>
        ))}
      </select>
    </label>
  );
}
