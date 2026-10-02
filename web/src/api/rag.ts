import { authHeaders } from "./auth";
import { API_BASE, ApiError, api } from "./client";
import type { ApiKeyCreated, ApiKeyInfo, Document, Library, LibrarySummary, LlmTestResult, OllamaSetupResult, OllamaStatus, ProcessingJob, Project, ProjectUpsert, ProviderCatalog, SearchHit, VerifyRequest } from "./types";

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

export const ragApi = {
  listLibraries: () => json<LibrarySummary[]>("/v1/libraries"),
  getLibrary: (id: string) => json<Library>(`/v1/libraries/${encodeURIComponent(id)}`),
  createLibrary: (name: string, description: string) => json<Library>("/v1/libraries", { method: "POST", body: JSON.stringify({ name, description }) }),
  updateLibrary: (id: string, name: string, description: string) => json<Library>(`/v1/libraries/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ name, description }) }),
  deleteLibrary: (id: string) => json<void>(`/v1/libraries/${encodeURIComponent(id)}`, { method: "DELETE" }),
  uploadDocuments: (id: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return json<Document[]>(`/v1/libraries/${encodeURIComponent(id)}/documents`, { method: "POST", body: form });
  },
  addUrl: (id: string, url: string, name: string) => json<Document>(`/v1/libraries/${encodeURIComponent(id)}/documents/url`, { method: "POST", body: JSON.stringify({ url, name }) }),
  deleteDocument: (id: string, documentId: string) => json<void>(`/v1/libraries/${encodeURIComponent(id)}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" }),
  reindexDocument: (id: string, documentId: string) => json<Document>(`/v1/libraries/${encodeURIComponent(id)}/documents/${encodeURIComponent(documentId)}/reindex`, { method: "POST" }),
  searchLibrary: (id: string, q: string) => json<SearchHit[]>(`/v1/libraries/${encodeURIComponent(id)}/search?q=${encodeURIComponent(q)}&limit=5`),

  listProjects: () => json<Project[]>("/v1/projects"),
  createProject: (body: ProjectUpsert) => json<Project>("/v1/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (id: string, body: ProjectUpsert) => json<Project>(`/v1/projects/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteProject: (id: string) => json<void>(`/v1/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
  effectiveLibraries: (id: string) => json<string[]>(`/v1/projects/${encodeURIComponent(id)}/libraries`),

  verify: (jobId: string, body: VerifyRequest) => json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(jobId)}/verify`, { method: "POST", body: JSON.stringify(body) }),
  factCheckDecisions: (jobId: string, decisions: { id: string; dismissed: boolean }[]) =>
    json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(jobId)}/verify/decisions`, { method: "PUT", body: JSON.stringify(decisions) }),
  setJobProject: (jobId: string, projectId: string | null) =>
    json<ProcessingJob>(`/v1/jobs/${encodeURIComponent(jobId)}/project${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`, { method: "PUT" }),
  getJob: api.getJob,

  catalog: () => json<ProviderCatalog>("/v1/providers/catalog"),
  testLlm: () => json<LlmTestResult>("/v1/providers/llm/test", { method: "POST" }),
  ollamaStatus: () => json<OllamaStatus>("/v1/providers/ollama/status"),
  ollamaSetup: (model?: string | null) => json<OllamaSetupResult>("/v1/providers/ollama/setup", { method: "POST", body: JSON.stringify({ model: model ?? null, start_server: true }) }),
  ollamaStart: () => json<{ running: boolean }>("/v1/providers/ollama/start", { method: "POST" }),
  cloneVoice: (jobId: string, name: string) => json<{ voice_id: string; name: string }>("/v1/providers/voice/clone", { method: "POST", body: JSON.stringify({ job_id: jobId, name, set_as_default: true }) }),
  listApiKeys: () => json<ApiKeyInfo[]>("/v1/api-keys"),
  createApiKey: (label: string) => json<ApiKeyCreated>("/v1/api-keys", { method: "POST", body: JSON.stringify({ label }) }),
  deleteApiKey: (prefix: string) => json<void>(`/v1/api-keys/${encodeURIComponent(prefix)}`, { method: "DELETE" }),
};
