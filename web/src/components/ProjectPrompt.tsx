import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { episodesApi } from "../api/episodes";
import { ragApi } from "../api/rag";
import type { ProcessingJob, Project } from "../api/types";

const DISMISS_KEY = "aipodcaster.projectPromptDismissed";

function dismissedIds(): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(DISMISS_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

function rememberDismissed(id: string): void {
  try {
    window.localStorage.setItem(DISMISS_KEY, JSON.stringify([...dismissedIds().filter((item) => item !== id), id].slice(-200)));
  } catch {
    /* storage unavailable */
  }
}

interface Props {
  job: ProcessingJob;
  projects: Project[];
  onJob: (job: ProcessingJob) => void;
  onProjects: (projects: Project[]) => void;
}

/**
 * Episodes without a project are easy to lose track of. This asks once per episode
 * (dialog) and then keeps a slim reminder banner until the episode is filed.
 */
export function ProjectPrompt({ job, projects, onJob, onProjects }: Props) {
  const { t } = useTranslation("job");
  const [open, setOpen] = useState(() => !job.project_id && !dismissedIds().includes(job.id));
  const [mode, setMode] = useState<"new" | "existing">(projects.length ? "existing" : "new");
  const [name, setName] = useState("");
  const [existing, setExisting] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstField = useRef<HTMLInputElement | HTMLSelectElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => firstField.current?.focus(), 0);
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && dismiss();
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  });

  if (job.project_id) return null;

  function dismiss() {
    rememberDismissed(job.id);
    setOpen(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let projectId = existing || projects[0]?.id || "";
      if (mode === "new") {
        const created = await ragApi.createProject({ name: (name || job.display_name || job.asset_name).trim().slice(0, 120), description: "", library_ids: [], linked_project_ids: [], online_fact_check: false });
        onProjects([created, ...projects]);
        projectId = created.id;
      }
      onJob(await episodesApi.updateMeta(job.id, { project_id: projectId }));
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not save the project"));
    } finally {
      setBusy(false);
    }
  }

  const form = (
    <form onSubmit={submit}>
      <div className="tabs" role="tablist" aria-label={t("Project choice")}>
        <button type="button" role="tab" className={`tab${mode === "new" ? " active" : ""}`} aria-selected={mode === "new"} onClick={() => setMode("new")}>
          {t("New project")}
        </button>
        <button type="button" role="tab" className={`tab${mode === "existing" ? " active" : ""}`} aria-selected={mode === "existing"} onClick={() => setMode("existing")} disabled={!projects.length}>
          {t("Existing project")}
        </button>
      </div>
      {mode === "new" ? (
        <div className="field">
          <label htmlFor="prompt-project-name">{t("Project (podcast or series) name")}</label>
          <input id="prompt-project-name" ref={(el) => void (firstField.current = el)} type="text" maxLength={120} value={name} placeholder={job.display_name || t("My podcast")} onChange={(e) => setName(e.target.value)} />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="prompt-project-existing">{t("Add to project")}</label>
          <select id="prompt-project-existing" ref={(el) => void (firstField.current = el)} value={existing || projects[0]?.id || ""} onChange={(e) => setExisting(e.target.value)}>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="btn-row">
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? t("Saving…") : mode === "new" ? t("Create project and add episode") : t("Add episode to project")}
        </button>
        <button type="button" className="btn" onClick={dismiss}>
          {t("Not now")}
        </button>
      </div>
    </form>
  );

  if (open)
    return (
      <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && dismiss()}>
        <div className="modal card" role="dialog" aria-modal="true" aria-labelledby="project-prompt-title">
          <h2 id="project-prompt-title">{t("Save this episode in a project")}</h2>
          <p className="muted">{t("A project is your podcast or series. It keeps episodes, fact-check libraries and publishing settings together, so nothing you add gets lost.")}</p>
          {form}
        </div>
      </div>
    );

  return (
    <div className="alert info project-banner" role="note">
      <span>{t("This episode is not in a project yet.")}</span>
      <button type="button" className="btn sm" onClick={() => setOpen(true)}>
        {t("Add to project")}
      </button>
    </div>
  );
}
