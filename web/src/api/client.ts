import { authHeaders, getUiApiKey } from "./auth";
import type { AppSettings, ApprovalRequest, JobSummary, ProcessingJob, ProviderStatus } from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...authHeaders(), ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((item: { msg?: string }) => item.msg ?? "Invalid input").join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/healthz"),
  listJobs: () => request<JobSummary[]>("/v1/jobs"),
  getJob: (id: string) => request<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}`),
  deleteJob: (id: string) => request<void>(`/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  reanalyze: (id: string) => request<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/reanalyze`, { method: "POST" }),
  updateTranscript: (id: string, segments: { id: number; text: string }[]) =>
    request<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/transcript`, { method: "PUT", body: JSON.stringify({ segments }) }),
  approve: (id: string, body: ApprovalRequest) =>
    request<ProcessingJob>(`/v1/jobs/${encodeURIComponent(id)}/approval`, { method: "POST", body: JSON.stringify(body) }),
  getSettings: () => request<AppSettings>("/v1/settings"),
  saveSettings: (settings: AppSettings) => request<AppSettings>("/v1/settings", { method: "PUT", body: JSON.stringify(settings) }),
  providers: () => request<ProviderStatus[]>("/v1/settings/providers"),
  originalAudioUrl: (id: string) => `${API_BASE}/v1/jobs/${encodeURIComponent(id)}/audio/original`,
  outputUrl: (id: string, name: string) => `${API_BASE}/v1/jobs/${encodeURIComponent(id)}/outputs/${encodeURIComponent(name)}`,
};

export function uploadRecording(file: File, onProgress?: (fraction: number) => void, projectId?: string | null): Promise<ProcessingJob> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (projectId) form.append("project_id", projectId);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/v1/jobs`);
    xhr.responseType = "json";
    if (getUiApiKey()) xhr.setRequestHeader("X-API-Key", getUiApiKey());
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error while uploading"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as ProcessingJob);
      else {
        const detail = (xhr.response as { detail?: string } | null)?.detail;
        reject(new ApiError(xhr.status, typeof detail === "string" ? detail : `Upload failed (${xhr.status})`));
      }
    };
    xhr.send(form);
  });
}
