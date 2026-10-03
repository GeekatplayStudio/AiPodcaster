import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { episodesApi } from "../api/episodes";
import { ragApi } from "../api/rag";
import type { JobSummary, Project } from "../api/types";
import { EpisodeTable } from "../components/EpisodeTable";
import { ContinueCard } from "../components/ContinueCard";
import { UploadPanel } from "../components/UploadPanel";
import { DEFAULT_FILTERS, filterEpisodes, groupByProject, moveItem, type EpisodeFilters, type SortKey } from "../lib/episodes";
import { isProcessing } from "../lib/format";

const FILTER_KEY = "aipodcaster.episodeFilters";

function loadFilters(): EpisodeFilters {
  try {
    const raw = window.localStorage.getItem(FILTER_KEY);
    return raw ? { ...DEFAULT_FILTERS, ...(JSON.parse(raw) as Partial<EpisodeFilters>) } : DEFAULT_FILTERS;
  } catch {
    return DEFAULT_FILTERS;
  }
}

export function LibraryPage({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation("library");
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [filters, setFilters] = useState<EpisodeFilters>(loadFilters);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [list, projectList] = await Promise.all([episodesApi.list({ include_archived: true }), ragApi.listProjects().catch(() => [])]);
      setJobs(list);
      setProjects(projectList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Could not load episodes"));
    }
  }, [t]);

  const polling = jobs?.some((job) => isProcessing(job.stage)) ?? false;
  useEffect(() => {
    const timer = window.setTimeout(refresh, 0);
    const interval = polling ? window.setInterval(refresh, 2500) : undefined;
    return () => {
      window.clearTimeout(timer);
      if (interval) window.clearInterval(interval);
    };
  }, [polling, refresh]);

  useEffect(() => {
    try {
      window.localStorage.setItem(FILTER_KEY, JSON.stringify(filters));
    } catch {
      /* ignore */
    }
  }, [filters]);

  const visible = useMemo(() => (jobs ? filterEpisodes(jobs, filters) : []), [jobs, filters]);
  const projectName = (id: string | null) => projects.find((p) => p.id === id)?.name ?? t("(deleted project)");
  const groups = filters.groupByProject ? groupByProject(visible, projectName) : [{ key: "all", title: "", items: visible }];
  const counts = { total: jobs?.length ?? 0, archived: jobs?.filter((j) => j.archived).length ?? 0, review: jobs?.filter((j) => j.stage === "waiting_for_approval" && !j.archived).length ?? 0 };

  const patch = (next: Partial<EpisodeFilters>) => setFilters((current) => ({ ...current, ...next }));

  async function act<T>(action: () => Promise<T>) {
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Action failed"));
    }
  }

  async function reorder(fromId: string, toId: string) {
    if (!jobs) return;
    const ordered = filterEpisodes(jobs, { ...filters, sort: "manual" });
    const from = ordered.findIndex((j) => j.id === fromId);
    const to = ordered.findIndex((j) => j.id === toId);
    const next = moveItem(ordered, from, to);
    setJobs((current) => current && [...next, ...current.filter((j) => !next.some((n) => n.id === j.id))]);
    await act(() => episodesApi.reorder(next.map((j) => j.id)));
  }

  function move(id: string, direction: -1 | 1) {
    const index = visible.findIndex((j) => j.id === id);
    const target = visible[index + direction];
    if (target) void reorder(id, target.id);
  }

  async function bulk(action: "archive" | "unarchive" | "delete") {
    if (selected.size === 0) return;
    if (action === "delete" && !window.confirm(t("Delete {{count}} episode(s) and all their files? This cannot be undone.", { count: selected.size }))) return;
    await act(() => episodesApi.bulk([...selected], action));
    setSelected(new Set());
  }

  async function downloadSelected() {
    for (const id of selected) {
      const job = await api.getJob(id).catch(() => null);
      const zip = job?.outputs.find((o) => o.name.endsWith("publish-kit.zip"));
      if (job && zip) await episodesApi.downloadWithAuth(api.outputUrl(job.id, zip.name), zip.name).catch(() => undefined);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{t("Episodes")}</h1>
          <p>
            {t("{{total}} episodes · {{review}} waiting for review · {{archived}} archived", { total: counts.total, review: counts.review, archived: counts.archived })}
          </p>
        </div>
        <button type="button" className="btn" onClick={() => setShowUpload((v) => !v)}>
          {showUpload ? t("Hide import") : t("New episode")}
        </button>
      </div>
      <ContinueCard existingIds={jobs ? jobs.map((job) => job.id) : null} />
      {showUpload && <UploadPanel onUploaded={(job) => onOpen(job.id)} />}
      <section className="card" style={{ marginTop: "1rem" }} aria-labelledby="library-title">
        <div className="card-title">
          <h2 id="library-title">{t("Library")}</h2>
          <div className="btn-row">
            <button type="button" className="btn sm" onClick={() => void refresh()}>
              {t("Refresh")}
            </button>
          </div>
        </div>
        <div className="filters">
          <input className="input" type="search" placeholder={t("Search name, file, tag…")} value={filters.query} onChange={(e) => patch({ query: e.target.value })} aria-label={t("Search episodes")} />
          <select className="input" value={filters.stage} onChange={(e) => patch({ stage: e.target.value as EpisodeFilters["stage"] })} aria-label={t("Status filter")}>
            <option value="all">{t("Any status")}</option>
            <option value="needs_review">{t("Needs review")}</option>
            <option value="ready">{t("Produced")}</option>
            <option value="failed">{t("Failed")}</option>
          </select>
          <select className="input" value={filters.source} onChange={(e) => patch({ source: e.target.value as EpisodeFilters["source"] })} aria-label={t("Source filter")}>
            <option value="all">{t("Audio & text")}</option>
            <option value="audio">{t("Audio")}</option>
            <option value="text">{t("Text")}</option>
          </select>
          <select className="input" value={filters.projectId} onChange={(e) => patch({ projectId: e.target.value })} aria-label={t("Project filter")}>
            <option value="all">{t("All projects")}</option>
            <option value="none">{t("No project")}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select className="input" value={filters.sort} onChange={(e) => patch({ sort: e.target.value as SortKey })} aria-label={t("Sort")}>
            <option value="manual">{t("Manual order")}</option>
            <option value="updated">{t("Recently updated")}</option>
            <option value="created">{t("Newest")}</option>
            <option value="name">{t("Name")}</option>
            <option value="duration">{t("Longest")}</option>
            <option value="words">{t("Most words")}</option>
          </select>
          <label className="checkbox">
            <input type="checkbox" checked={filters.groupByProject} onChange={(e) => patch({ groupByProject: e.target.checked })} /> {t("Group by project")}
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={filters.flaggedOnly} onChange={(e) => patch({ flaggedOnly: e.target.checked })} /> {t("Fact flags only")}
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={filters.showArchived} onChange={(e) => patch({ showArchived: e.target.checked })} /> {t("Show archived")}
          </label>
        </div>
        {selected.size > 0 && (
          <div className="bulk-bar" role="toolbar" aria-label={t("Bulk actions")}>
            <strong>{t("{{count}} selected", { count: selected.size })}</strong>
            <button type="button" className="btn sm" onClick={() => void bulk("archive")}>
              {t("Archive")}
            </button>
            <button type="button" className="btn sm" onClick={() => void bulk("unarchive")}>
              {t("Unarchive")}
            </button>
            <button type="button" className="btn sm" onClick={() => void downloadSelected()}>
              {t("Download kits")}
            </button>
            <button type="button" className="btn sm danger" onClick={() => void bulk("delete")}>
              {t("Delete")}
            </button>
            <button type="button" className="btn sm" onClick={() => setSelected(new Set())}>
              {t("Clear")}
            </button>
          </div>
        )}
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {jobs === null && !error && <p className="muted">{t("Loading…")}</p>}
        {jobs && visible.length === 0 && <div className="empty">{jobs.length === 0 ? t("No episodes yet. Import a recording or transcript above.") : t("Nothing matches the current filters.")}</div>}
        {groups.map((group) => (
          <div key={group.key}>
            {group.title && (
              <h3 className="group-title">
                {group.key === "none" ? t("No project") : group.title} <span className="muted small">({group.items.length})</span>
              </h3>
            )}
            {group.items.length > 0 && (
              <EpisodeTable
                items={group.items}
                projects={projects}
                selected={selected}
                manualOrder={filters.sort === "manual" && !filters.groupByProject}
                onSelect={(id, checked) =>
                  setSelected((current) => {
                    const next = new Set(current);
                    if (checked) next.add(id);
                    else next.delete(id);
                    return next;
                  })
                }
                onOpen={onOpen}
                onRename={(id, name) => void act(() => episodesApi.updateMeta(id, { display_name: name }))}
                onMove={move}
                onDrop={(from, to) => void reorder(from, to)}
                onProject={(id, projectId) => void act(() => episodesApi.updateMeta(id, projectId ? { project_id: projectId } : { clear_project: true }))}
              />
            )}
          </div>
        ))}
      </section>
    </>
  );
}
