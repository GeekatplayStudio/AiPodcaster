import type { JobStage, JobSummary, SourceKind } from "../api/types";

export type SortKey = "manual" | "updated" | "created" | "name" | "duration" | "words";

export interface EpisodeFilters {
  query: string;
  stage: JobStage | "all" | "needs_review" | "ready";
  source: SourceKind | "all";
  projectId: string | "all" | "none";
  showArchived: boolean;
  flaggedOnly: boolean;
  sort: SortKey;
  groupByProject: boolean;
}

export const DEFAULT_FILTERS: EpisodeFilters = { query: "", stage: "all", source: "all", projectId: "all", showArchived: false, flaggedOnly: false, sort: "manual", groupByProject: false };

export function filterEpisodes(items: JobSummary[], filters: EpisodeFilters): JobSummary[] {
  const needle = filters.query.trim().toLowerCase();
  let result = items.filter((item) => {
    if (!filters.showArchived && item.archived) return false;
    if (filters.source !== "all" && item.source_kind !== filters.source) return false;
    if (filters.projectId === "none" && item.project_id) return false;
    if (filters.projectId !== "all" && filters.projectId !== "none" && item.project_id !== filters.projectId) return false;
    if (filters.flaggedOnly && item.flagged_claims === 0) return false;
    if (filters.stage === "needs_review" && item.stage !== "waiting_for_approval") return false;
    if (filters.stage === "ready" && item.stage !== "complete") return false;
    if (filters.stage !== "all" && filters.stage !== "needs_review" && filters.stage !== "ready" && item.stage !== filters.stage) return false;
    if (needle && ![item.display_name, item.asset_name, ...item.tags, item.language ?? ""].some((text) => text.toLowerCase().includes(needle))) return false;
    return true;
  });
  result = sortEpisodes(result, filters.sort);
  return result;
}

export function sortEpisodes(items: JobSummary[], sort: SortKey): JobSummary[] {
  const copy = [...items];
  switch (sort) {
    case "updated":
      return copy.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    case "created":
      return copy.sort((a, b) => b.created_at.localeCompare(a.created_at));
    case "name":
      return copy.sort((a, b) => a.display_name.localeCompare(b.display_name));
    case "duration":
      return copy.sort((a, b) => b.duration_ms - a.duration_ms);
    case "words":
      return copy.sort((a, b) => b.word_count - a.word_count);
    default:
      return copy.sort((a, b) => a.order - b.order || b.created_at.localeCompare(a.created_at));
  }
}

export function groupByProject(items: JobSummary[], projectName: (id: string | null) => string): { key: string; title: string; items: JobSummary[] }[] {
  const groups = new Map<string, JobSummary[]>();
  for (const item of items) {
    const key = item.project_id ?? "none";
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.entries()].map(([key, list]) => ({ key, title: key === "none" ? "No project" : projectName(key), items: list })).sort((a, b) => a.title.localeCompare(b.title));
}

export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const copy = [...list];
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}
