import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { uiLocale } from "../lib/format";
import { api } from "../api/client";
import { episodesApi } from "../api/episodes";
import type { ProcessingJob } from "../api/types";

const DRAFT_KEY = "aipodcaster.textDraft";

interface TextDraft {
  text: string;
  name: string;
  wpm: number;
  language: string;
}

function loadDraft(): TextDraft {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (raw) return { text: "", name: "", wpm: 150, language: "auto", ...(JSON.parse(raw) as Partial<TextDraft>) };
  } catch {
    /* storage unavailable */
  }
  return { text: "", name: "", wpm: 150, language: "auto" };
}

function dateStamp(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

const TEXT_ACCEPT = ".txt,.md,.markdown,.srt,.vtt,.pdf,.docx,.html,.htm,.rtf,.json,.csv,.epub";

export function detectPastedFormat(text: string): string {
  const head = text.trimStart().slice(0, 2000);
  if (head.startsWith("WEBVTT")) return "WebVTT captions";
  if (/\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->/.test(head)) return "SRT captions";
  const lines = head.split("\n").filter((l) => l.trim());
  const stamped = lines.filter((l) => /^\s*[[(]?\d{1,2}:\d{2}/.test(l)).length;
  if (lines.length && stamped >= Math.max(2, lines.length / 3)) return "timestamped transcript";
  const spoken = lines.filter((l) => /^\s*\p{Lu}[\p{L}\p{N} ._'-]{0,30}:\s/u.test(l)).length;
  if (lines.length && spoken >= Math.max(2, lines.length / 3)) return "speaker dialogue";
  return "plain text / script";
}

export function TextImportPanel({ projectId, onCreated }: { projectId: string | null; onCreated: (job: ProcessingJob) => void }) {
  const { t } = useTranslation("library");
  const [initial] = useState(loadDraft);
  const [text, setText] = useState(initial.text);
  const [name, setName] = useState(initial.name);
  const [wpm, setWpm] = useState(initial.wpm);
  const [language, setLanguage] = useState(initial.language);
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [placeholderDate] = useState(() => dateStamp());

  useEffect(() => {
    let cancelled = false;
    api
      .info()
      .then((info) => !cancelled && setLanguages(info.languages))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep the unsent paste across reloads and navigation.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        if (text || name) window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ text, name, wpm, language }));
        else window.localStorage.removeItem(DRAFT_KEY);
      } catch {
        /* storage unavailable */
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [text, name, wpm, language]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  async function submitText() {
    setBusy(true);
    setError(null);
    try {
      onCreated(await episodesApi.createFromText(text, name.trim(), projectId, wpm, language === "auto" ? null : language));
      setText("");
      setName("");
      try {
        window.localStorage.removeItem(DRAFT_KEY);
      } catch {
        /* storage unavailable */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Import failed"));
    } finally {
      setBusy(false);
    }
  }

  async function submitFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await episodesApi.uploadTextFile(file, projectId, wpm));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Import failed"));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="text-import">
      <div
        className="dropzone compact"
        role="button"
        tabIndex={0}
        onClick={() => !busy && fileInput.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void submitFile(e.dataTransfer.files?.[0]);
        }}
      >
        <input ref={fileInput} type="file" accept={TEXT_ACCEPT} onChange={(e) => void submitFile(e.target.files?.[0])} aria-label={t("Choose a transcript document")} />
        <strong>{t("Drop a transcript or script file")}</strong>
        <span className="muted small">{t("TXT, Markdown, SRT, VTT, PDF, Word, HTML, EPUB. The format is detected automatically.")}</span>
      </div>
      <div className="field" style={{ marginTop: 10 }}>
        <label htmlFor="paste-text">
          {words ? t("…or paste text ({{words}} words · looks like {{format}})", { words: words.toLocaleString(uiLocale()), format: t(detectPastedFormat(text)) }) : t("…or paste text")}
        </label>
        <textarea id="paste-text" style={{ minHeight: 140 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={`${t("HOST: Welcome back to the show.")}\n${t("[00:12] Today we talk about…")}`} />
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="paste-name">{t("Episode name")}</label>
          <input id="paste-name" type="text" maxLength={180} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("Episode {{date}}", { date: placeholderDate })} />
        </div>
        <div className="field">
          <label htmlFor="paste-language">{t("Language")}</label>
          <select id="paste-language" value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="auto">{t("Detect automatically")}</option>
            {Object.entries(languages).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
          <span className="hint">{t("Used for filler words, profanity and show notes.")}</span>
        </div>
        <div className="field">
          <label htmlFor="paste-wpm">{t("Speaking pace (words/min)")}</label>
          <input id="paste-wpm" type="number" min={80} max={260} value={wpm} onChange={(e) => setWpm(Number(e.target.value))} />
          <span className="hint">{t("Used to estimate timing for text without timestamps.")}</span>
        </div>
        <div className="field" style={{ alignSelf: "end" }}>
          <button type="button" className="btn primary" onClick={() => void submitText()} disabled={busy || text.trim().length < 20}>
            {busy ? t("Importing…") : t("Create episode from text")}
          </button>
        </div>
      </div>
      <p className="muted small">
        {t("Text episodes are voiced with the synthetic speech provider from Settings. Speaker labels such as “HOST:” are kept for review but not read aloud.")}
      </p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
