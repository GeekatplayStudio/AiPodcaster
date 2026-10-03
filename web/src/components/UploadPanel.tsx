import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, uploadRecording } from "../api/client";
import { ragApi } from "../api/rag";
import type { ApiInfo, ProcessingJob, Project } from "../api/types";
import { LongFileNotice } from "./LongFileNotice";
import { isLongRecording, readMediaDuration } from "../lib/estimate";
import { LinkImportPanel } from "./LinkImportPanel";
import { TextImportPanel } from "./TextImportPanel";
import { validateFile } from "../lib/edits";
import { formatBytes } from "../lib/format";

const MAX_BYTES = 8 * 1024 * 1024 * 1024;

export function UploadPanel({ onUploaded }: { onUploaded: (job: ProcessingJob) => void }) {
  const { t } = useTranslation("library");
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [mode, setMode] = useState<"voice" | "link" | "text">(() => {
    try {
      const stored = window.localStorage.getItem("aipodcaster.importMode");
      return stored === "link" || stored === "text" ? stored : "voice";
    } catch {
      return "voice";
    }
  });
  const [info, setInfo] = useState<ApiInfo | null>(null);
  const [pendingLong, setPendingLong] = useState<{ file: File; duration: number } | null>(null);
  const [projectId, setProjectId] = useState<string>(() => {
    try {
      return window.localStorage.getItem("aipodcaster.project") ?? "";
    } catch {
      return "";
    }
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void ragApi.listProjects().then(setProjects).catch(() => undefined);
      void api.info().then(setInfo).catch(() => undefined);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function chooseMode(next: "voice" | "link" | "text") {
    setMode(next);
    try {
      window.localStorage.setItem("aipodcaster.importMode", next);
    } catch {
      /* storage unavailable */
    }
  }

  function chooseProject(value: string) {
    setProjectId(value);
    try {
      window.localStorage.setItem("aipodcaster.project", value);
    } catch {
      /* storage unavailable */
    }
  }

  async function handleFile(file: File | undefined, confirmed = false) {
    if (!file) return;
    const problem = validateFile(file, MAX_BYTES);
    setError(problem);
    if (problem) return;
    if (!confirmed) {
      // Warn before long uploads: read the duration locally, without uploading anything yet.
      const duration = await readMediaDuration(file);
      if (isLongRecording(duration ?? 0, file.size, info)) {
        setPendingLong({ file, duration: duration ?? 0 });
        return;
      }
    }
    setPendingLong(null);
    setFileName(`${file.name} · ${formatBytes(file.size)}`);
    setProgress(0);
    try {
      const job = await uploadRecording(file, setProgress, projectId || null);
      setProgress(null);
      onUploaded(job);
    } catch (err) {
      setProgress(null);
      setError(err instanceof Error ? err.message : t("Upload failed"));
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
        <label htmlFor="upload-project">{t("Project for new uploads")}</label>
        <select id="upload-project" value={projects.some((p) => p.id === projectId) ? projectId : ""} onChange={(e) => chooseProject(e.target.value)} disabled={busy}>
          <option value="">{t("No project")}</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <span className="hint">{t("The project decides which knowledge libraries are used for fact checking.")}</span>
      </div>
      <div className="tabs" role="tablist" aria-label={t("Import type")}>
        <button type="button" role="tab" className={`tab${mode === "voice" ? " active" : ""}`} aria-selected={mode === "voice"} onClick={() => chooseMode("voice")}>
          {t("Voice recording")}
        </button>
        <button type="button" role="tab" className={`tab${mode === "link" ? " active" : ""}`} aria-selected={mode === "link"} onClick={() => chooseMode("link")}>
          {t("Link or large file")}
        </button>
        <button type="button" role="tab" className={`tab${mode === "text" ? " active" : ""}`} aria-selected={mode === "text"} onClick={() => chooseMode("text")}>
          {t("Transcript / text")}
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
        <input ref={inputRef} type="file" accept="audio/*,video/mp4,video/quicktime,video/webm" onChange={onChange} aria-label={t("Choose a recording")} />
        <strong id="upload-title">{busy ? t("Uploading…") : t("Drop a raw recording here or click to choose")}</strong>
        <span className="muted small">
          {t("Audio or video: WAV, MP3, M4A, FLAC, OGG, WEBM, MP4, MOV · up to {{size}} through the browser. For bigger files use “Link or large file”. The original is never modified.", { size: formatBytes(MAX_BYTES) })}
        </span>
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
      {mode === "voice" && pendingLong && (
        <LongFileNotice
          fileName={pendingLong.file.name}
          sizeBytes={pendingLong.file.size}
          durationSeconds={pendingLong.duration}
          info={info}
          onConfirm={() => void handleFile(pendingLong.file, true)}
          onCancel={() => {
            setPendingLong(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      )}
      {mode === "voice" && error && (
        <div className="alert error" role="alert" style={{ marginTop: "0.75rem" }}>
          {error}
        </div>
      )}
    </section>
  );
}
