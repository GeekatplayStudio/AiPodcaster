import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { uploadRecording } from "../api/client";
import { ragApi } from "../api/rag";
import type { ProcessingJob, Project } from "../api/types";
import { LinkImportPanel } from "./LinkImportPanel";
import { TextImportPanel } from "./TextImportPanel";
import { validateFile } from "../lib/edits";
import { formatBytes } from "../lib/format";

const MAX_BYTES = 8 * 1024 * 1024 * 1024;

export function UploadPanel({ onUploaded }: { onUploaded: (job: ProcessingJob) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [mode, setMode] = useState<"voice" | "link" | "text">("voice");
  const [projectId, setProjectId] = useState<string>(() => {
    try {
      return window.localStorage.getItem("aipodcaster.project") ?? "";
    } catch {
      return "";
    }
  });

  useEffect(() => {
    const timer = window.setTimeout(() => void ragApi.listProjects().then(setProjects).catch(() => undefined), 0);
    return () => window.clearTimeout(timer);
  }, []);

  function chooseProject(value: string) {
    setProjectId(value);
    try {
      window.localStorage.setItem("aipodcaster.project", value);
    } catch {
      /* storage unavailable */
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    const problem = validateFile(file, MAX_BYTES);
    setError(problem);
    if (problem) return;
    setFileName(`${file.name} · ${formatBytes(file.size)}`);
    setProgress(0);
    try {
      const job = await uploadRecording(file, setProgress, projectId || null);
      setProgress(null);
      onUploaded(job);
    } catch (err) {
      setProgress(null);
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void handleFile(event.dataTransfer.files?.[0]);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    void handleFile(event.target.files?.[0]);
  }

  const busy = progress !== null;
  return (
    <section aria-labelledby="upload-title">
      <div className="field" style={{ maxWidth: 420 }}>
        <label htmlFor="upload-project">Project for new uploads</label>
        <select id="upload-project" value={projects.some((p) => p.id === projectId) ? projectId : ""} onChange={(e) => chooseProject(e.target.value)} disabled={busy}>
          <option value="">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <span className="hint">The project decides which knowledge libraries are used for fact checking.</span>
      </div>
      <div className="tabs" role="tablist" aria-label="Import type">
        <button type="button" role="tab" className={`tab${mode === "voice" ? " active" : ""}`} aria-selected={mode === "voice"} onClick={() => setMode("voice")}>
          Voice recording
        </button>
        <button type="button" role="tab" className={`tab${mode === "link" ? " active" : ""}`} aria-selected={mode === "link"} onClick={() => setMode("link")}>
          Link or large file
        </button>
        <button type="button" role="tab" className={`tab${mode === "text" ? " active" : ""}`} aria-selected={mode === "text"} onClick={() => setMode("text")}>
          Transcript / text
        </button>
      </div>
      {mode === "link" && <LinkImportPanel projectId={projectId || null} onCreated={onUploaded} />}
      {mode === "text" && <TextImportPanel projectId={projectId || null} onCreated={onUploaded} />}
      {mode === "voice" && (
      <div
        className={`dropzone${dragging ? " active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !busy) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-disabled={busy}
      >
        <input ref={inputRef} type="file" accept="audio/*,video/mp4,video/quicktime,video/webm" onChange={onChange} aria-label="Choose a recording" />
        <strong id="upload-title">{busy ? "Uploading…" : "Drop a raw recording here or click to choose"}</strong>
        <span className="muted small">Audio or video: WAV, MP3, M4A, FLAC, OGG, WEBM, MP4, MOV · up to {formatBytes(MAX_BYTES)} through the browser. For bigger files use “Link or large file”. The original is never modified.</span>
        {busy && (
          <div style={{ marginTop: "1rem" }}>
            <div className="muted small" style={{ marginBottom: 6 }}>
              {fileName}
            </div>
            <div className="progress" role="progressbar" aria-valuenow={Math.round((progress ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${Math.round((progress ?? 0) * 100)}%` }} />
            </div>
          </div>
        )}
      </div>
      )}
      {mode === "voice" && error && (
        <div className="alert error" role="alert" style={{ marginTop: "0.75rem" }}>
          {error}
        </div>
      )}
    </section>
  );
}
