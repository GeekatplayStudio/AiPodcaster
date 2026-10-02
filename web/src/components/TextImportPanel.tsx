import { useRef, useState } from "react";
import { episodesApi } from "../api/episodes";
import type { ProcessingJob } from "../api/types";

const TEXT_ACCEPT = ".txt,.md,.markdown,.srt,.vtt,.pdf,.docx,.html,.htm,.rtf,.json,.csv,.epub";

export function detectPastedFormat(text: string): string {
  const head = text.trimStart().slice(0, 2000);
  if (head.startsWith("WEBVTT")) return "WebVTT captions";
  if (/\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->/.test(head)) return "SRT captions";
  const lines = head.split("\n").filter((l) => l.trim());
  const stamped = lines.filter((l) => /^\s*[[(]?\d{1,2}:\d{2}/.test(l)).length;
  if (lines.length && stamped >= Math.max(2, lines.length / 3)) return "timestamped transcript";
  const spoken = lines.filter((l) => /^\s*[A-Z][A-Za-z0-9 ._'-]{0,30}:\s/.test(l)).length;
  if (lines.length && spoken >= Math.max(2, lines.length / 3)) return "speaker dialogue";
  return "plain text / script";
}

export function TextImportPanel({ projectId, onCreated }: { projectId: string | null; onCreated: (job: ProcessingJob) => void }) {
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [wpm, setWpm] = useState(150);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  async function submitText() {
    setBusy(true);
    setError(null);
    try {
      onCreated(await episodesApi.createFromText(text, name.trim() || "Pasted transcript", projectId, wpm));
      setText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
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
      setError(err instanceof Error ? err.message : "Import failed");
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
        <input ref={fileInput} type="file" accept={TEXT_ACCEPT} onChange={(e) => void submitFile(e.target.files?.[0])} aria-label="Choose a transcript document" />
        <strong>Drop a transcript or script file</strong>
        <span className="muted small">TXT, Markdown, SRT, VTT, PDF, Word, HTML, EPUB. The format is detected automatically.</span>
      </div>
      <div className="field" style={{ marginTop: 10 }}>
        <label htmlFor="paste-text">…or paste text {words ? `(${words.toLocaleString()} words · looks like ${detectPastedFormat(text)})` : ""}</label>
        <textarea id="paste-text" style={{ minHeight: 140 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={"HOST: Welcome back to the show.\n[00:12] Today we talk about…"} />
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="paste-name">Episode name</label>
          <input id="paste-name" type="text" maxLength={180} value={name} onChange={(e) => setName(e.target.value)} placeholder="Pasted transcript" />
        </div>
        <div className="field">
          <label htmlFor="paste-wpm">Speaking pace (words/min)</label>
          <input id="paste-wpm" type="number" min={80} max={260} value={wpm} onChange={(e) => setWpm(Number(e.target.value))} />
          <span className="hint">Used to estimate timing for text without timestamps.</span>
        </div>
        <div className="field" style={{ alignSelf: "end" }}>
          <button type="button" className="btn primary" onClick={() => void submitText()} disabled={busy || text.trim().length < 20}>
            {busy ? "Importing…" : "Create episode from text"}
          </button>
        </div>
      </div>
      <p className="muted small">Text episodes are voiced with the synthetic speech provider from Settings. Speaker labels such as “HOST:” are kept for review but not read aloud.</p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
