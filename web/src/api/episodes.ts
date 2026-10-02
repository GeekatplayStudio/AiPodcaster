import { authHeaders, getUiApiKey } from "./auth";
import { API_BASE, ApiError } from "./client";
import type { JobStats, JobSummary, ProcessingJob, PublishKit, PublishTarget, TargetKind } from "./types";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...authHeaders(), ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface ListFilters {
  include_archived?: boolean;
  project_id?: string;
  q?: string;
}

export const episodesApi = {
  list: (filters: ListFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.include_archived) params.set("include_archived", "true");
    if (filters.project_id) params.set("project_id", filters.project_id);
    if (filters.q) params.set("q", filters.q);
    const query = params.toString();
    return json<JobSummary[]>(`/v1/jobs${query ? `?${query}` : ""}`);
  },
  createFromText: (text: string, name: string, projectId: string | null, wordsPerMinute: number) =>
    json<ProcessingJob>("/v1/jobs/text", { method: "POST", body: JSON.stringify({ text, name, project_id: projectId, words_per_minute: wordsPerMinute }) }),
  uploadTextFile: (file: File, projectId: string | null, wordsPerMinute: number) => {
    const form = new FormData();
    form.append("file", file, file.name);
    const params = new URLSearchParams({ words_per_minute: String(wordsPerMinute) });
    if (projectId) params.set("project_id", projectId);
    return json<ProcessingJob>(`/v1/jobs/text/upload?${params}`, { method: "POST", body: form });
  },
  updateMeta: (id: string, body: { display_name?: string; archived?: boolean; project_id?: string | null; clear_project?: boolean; tags?: string[]; notes?: string }) =>
    json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/meta`, { method: "PATCH", body: JSON.stringify(body) }),
  reorder: (ids: string[]) => json<JobSummary[]>("/v1/jobs/reorder", { method: "POST", body: JSON.stringify({ ids }) }),
  bulk: (ids: string[], action: "archive" | "unarchive" | "delete") => json<JobSummary[]>("/v1/jobs/bulk", { method: "POST", body: JSON.stringify({ ids, action }) }),
  stats: (id: string) => json<JobStats>(`/v1/jobs/${encodeURIComponent(id)}/stats`),

  publishCatalog: () => json<TargetKind[]>("/v1/publish/catalog"),
  listTargets: () => json<PublishTarget[]>("/v1/publish/targets"),
  createTarget: (body: { name: string; kind: string; config: Record<string, string>; enabled: boolean }) => json<PublishTarget>("/v1/publish/targets", { method: "POST", body: JSON.stringify(body) }),
  updateTarget: (id: string, body: { name: string; kind: string; config: Record<string, string>; enabled: boolean }) =>
    json<PublishTarget>(`/v1/publish/targets/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTarget: (id: string) => json<void>(`/v1/publish/targets/${encodeURIComponent(id)}`, { method: "DELETE" }),
  generateKit: (id: string) => json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/kit/generate`, { method: "POST" }),
  saveKit: (id: string, kit: PublishKit) => json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/kit`, { method: "PUT", body: JSON.stringify(kit) }),
  makeThumbnail: (id: string, prompt: string, size: "square" | "youtube") =>
    json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/kit/thumbnail`, { method: "POST", body: JSON.stringify({ prompt, size }) }),
  uploadThumbnail: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/kit/thumbnail/upload`, { method: "POST", body: form });
  },
  publish: (id: string, targetId: string) => json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/publish`, { method: "POST", body: JSON.stringify({ target_id: targetId }) }),
  thumbnailUrl: (id: string, cacheKey: string) => `${API_BASE}/v1/jobs/${encodeURIComponent(id)}/kit/thumbnail?v=${encodeURIComponent(cacheKey)}`,
  packageUrl: (id: string) => `${API_BASE}/v1/jobs/${encodeURIComponent(id)}/publish/package`,
  downloadWithAuth: async (url: string, filename: string) => {
    const response = await fetch(url, { headers: getUiApiKey() ? { "X-API-Key": getUiApiKey() } : {} });
    if (!response.ok) throw new ApiError(response.status, response.statusText);
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(href);
  },
};
