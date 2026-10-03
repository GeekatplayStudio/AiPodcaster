import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ragApi } from "../api/rag";
import type { LibrarySummary, Project, ProjectUpsert } from "../api/types";

const EMPTY: ProjectUpsert = { name: "", description: "", library_ids: [], linked_project_ids: [], online_fact_check: false };

export function ProjectsPage() {
  const { t } = useTranslation("knowledge");
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [libraries, setLibraries] = useState<LibrarySummary[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<ProjectUpsert>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [p, l] = await Promise.all([ragApi.listProjects(), ragApi.listLibraries()]);
      setProjects(p);
      setLibraries(l);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not load projects"));
    }
  }, [t]);

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  function startNew() {
    setEditing("new");
    setForm(EMPTY);
  }

  function startEdit(project: Project) {
    setEditing(project.id);
    setForm({ name: project.name, description: project.description, library_ids: project.library_ids, linked_project_ids: project.linked_project_ids, online_fact_check: project.online_fact_check });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form.name.trim() || !editing) return;
    setSaving(true);
    try {
      if (editing === "new") await ragApi.createProject({ ...form, name: form.name.trim() });
      else await ragApi.updateProject(editing, { ...form, name: form.name.trim() });
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Save failed"));
    } finally {
      setSaving(false);
    }
  }

  async function remove(project: Project) {
    if (!window.confirm(t("Delete project \"{{name}}\"? Episodes keep their files but lose the project link.", { name: project.name }))) return;
    try {
      await ragApi.deleteProject(project.id);
      if (editing === project.id) setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Delete failed"));
    }
  }

  const toggle = (key: "library_ids" | "linked_project_ids", id: string) =>
    setForm((current) => ({ ...current, [key]: current[key].includes(id) ? current[key].filter((item) => item !== id) : [...current[key], id] }));

  const libraryName = (id: string) => libraries.find((l) => l.id === id)?.name ?? t("(deleted library)");
  const projectName = (id: string) => projects?.find((p) => p.id === id)?.name ?? t("(deleted project)");

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{t("Projects")}</h1>
          <p>{t("A project is a podcast or series. Each project chooses which knowledge libraries, and which other projects' libraries, are used to fact-check its episodes.")}</p>
        </div>
        <button type="button" className="btn primary" onClick={startNew}>
          {t("New project")}
        </button>
      </div>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      <div className="review-layout">
        <section className="card" aria-labelledby="project-list">
          <h2 id="project-list">{t("All projects")}</h2>
          {projects === null && <p className="muted">{t("Loading…")}</p>}
          {projects && projects.length === 0 && <div className="empty">{t("No projects yet. Create one to group episodes and pick libraries for fact checking.")}</div>}
          <div className="outputs">
            {projects?.map((project) => (
              <div className="output" key={project.id} style={{ alignItems: "flex-start" }}>
                <div className="meta" style={{ whiteSpace: "normal" }}>
                  <strong>{project.name}</strong>
                  <span className="muted small" style={{ display: "block" }}>
                    {project.description}
                  </span>
                  <span className="small" style={{ display: "block", marginTop: 4 }}>
                    {t("Libraries: {{names}}", { names: project.library_ids.length ? project.library_ids.map(libraryName).join(", ") : t("none") })}
                    {project.linked_project_ids.length ? ` · ${t("inherits from: {{names}}", { names: project.linked_project_ids.map(projectName).join(", ") })}` : ""}
                    {project.online_fact_check ? ` · ${t("online check on")}` : ""}
                  </span>
                </div>
                <div className="btn-row">
                  <button type="button" className="btn sm" onClick={() => startEdit(project)}>
                    {t("Edit")}
                  </button>
                  <button type="button" className="btn sm danger" onClick={() => void remove(project)}>
                    {t("Delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
        {editing && (
          <section className="card" aria-labelledby="project-form">
            <h2 id="project-form">{editing === "new" ? t("New project") : t("Edit project")}</h2>
            <form onSubmit={save}>
              <div className="field">
                <label htmlFor="project-name">{t("Name")}</label>
                <input id="project-name" type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={120} required />
              </div>
              <div className="field">
                <label htmlFor="project-desc">{t("Description")}</label>
                <textarea id="project-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength={1000} />
              </div>
              <fieldset className="field" style={{ border: "none", padding: 0 }}>
                <legend style={{ fontWeight: 600, fontSize: "0.9rem" }}>{t("Libraries used for fact checking")}</legend>
                {libraries.length === 0 && <span className="hint">{t("No libraries yet. Create them on the Libraries page.")}</span>}
                {libraries.map((library) => (
                  <label key={library.id} className="checkbox" style={{ marginBottom: 4 }}>
                    <input type="checkbox" checked={form.library_ids.includes(library.id)} onChange={() => toggle("library_ids", library.id)} />
                    {library.name} <span className="muted small">{t("({{count}} docs)", { count: library.ready_count })}</span>
                  </label>
                ))}
              </fieldset>
              <fieldset className="field" style={{ border: "none", padding: 0 }}>
                <legend style={{ fontWeight: 600, fontSize: "0.9rem" }}>{t("Also use libraries of these projects")}</legend>
                {projects?.filter((p) => p.id !== editing).length === 0 && <span className="hint">{t("No other projects.")}</span>}
                {projects
                  ?.filter((p) => p.id !== editing)
                  .map((project) => (
                    <label key={project.id} className="checkbox" style={{ marginBottom: 4 }}>
                      <input type="checkbox" checked={form.linked_project_ids.includes(project.id)} onChange={() => toggle("linked_project_ids", project.id)} />
                      {project.name}
                    </label>
                  ))}
              </fieldset>
              <label className="checkbox" style={{ marginBottom: 12 }}>
                <input type="checkbox" checked={form.online_fact_check} onChange={(e) => setForm({ ...form, online_fact_check: e.target.checked })} />
                {t("Check against Wikipedia by default")}
              </label>
              <div className="btn-row">
                <button type="submit" className="btn primary" disabled={saving}>
                  {saving ? t("Saving…") : t("Save project")}
                </button>
                <button type="button" className="btn" onClick={() => setEditing(null)}>
                  {t("Cancel")}
                </button>
              </div>
            </form>
          </section>
        )}
      </div>
    </>
  );
}
