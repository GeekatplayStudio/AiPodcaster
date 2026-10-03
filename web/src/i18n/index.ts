/**
 * UI translations (i18next). Keys are the English source strings, so English needs
 * no resource file and any missing translation falls back to readable English.
 *
 * Namespaces map to areas of the app; each lives in src/i18n/locales/<lng>/<ns>.json:
 *   common    shared words, stage and edit-type labels, header, theme and language menus
 *   library   episode library, import panels, app shell
 *   job       episode review page and its panels
 *   insights  statistics and publish pages
 *   settings  settings page and provider cards
 *   knowledge knowledge libraries and projects
 */
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

export const UI_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
  { code: "uk", label: "Українська" },
  { code: "es", label: "Español" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
] as const;

export const NAMESPACES = ["common", "library", "job", "insights", "settings", "knowledge"] as const;
export const LANGUAGE_STORAGE_KEY = "aipodcaster.lang";

type Dictionary = Record<string, string>;
// Each locale file becomes its own chunk, fetched only when that language is used.
// English needs no files: the keys are the English text.
const loaders = import.meta.glob<{ default: Dictionary }>("./locales/*/*.json");

const lazyBackend = {
  type: "backend" as const,
  init() {},
  read(language: string, namespace: string, callback: (error: unknown, data: Dictionary | boolean) => void) {
    const load = loaders[`./locales/${language}/${namespace}.json`];
    if (!load) {
      callback(null, {});
      return;
    }
    load()
      .then((module) => callback(null, module.default))
      .catch((error) => callback(error, false));
  },
};

void i18n
  .use(lazyBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "en",
    supportedLngs: UI_LANGUAGES.map((language) => language.code),
    nonExplicitSupportedLngs: true,
    load: "languageOnly",
    ns: [...NAMESPACES],
    defaultNS: "common",
    fallbackNS: "common",
    keySeparator: false,
    nsSeparator: false,
    returnEmptyString: false,
    interpolation: { escapeValue: false },
    // Render English immediately and swap in the translation when its chunk arrives.
    react: { useSuspense: false },
    detection: { order: ["localStorage", "navigator"], lookupLocalStorage: LANGUAGE_STORAGE_KEY, caches: ["localStorage"] },
  });

const syncDocumentLanguage = (language: string) => {
  if (typeof document !== "undefined") document.documentElement.lang = language;
};
syncDocumentLanguage(i18n.language);
i18n.on("languageChanged", syncDocumentLanguage);

export default i18n;
