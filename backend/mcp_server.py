"""AiPodcaster MCP server.

Exposes the running AiPodcaster API as Model Context Protocol tools so agents
(desktop assistants, IDE agents, custom agents) can upload recordings,
review transcripts, run fact checks, manage libraries and render episodes.

Run (stdio, for desktop clients):
    python mcp_server.py
Run over HTTP (for remote agents):
    python mcp_server.py --http --port 8765

Environment:
    AIPODCASTER_URL      API base URL (default http://127.0.0.1:8000)
    AIPODCASTER_API_KEY  key created in Settings → API access (required when keys exist)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

API_URL = os.environ.get("AIPODCASTER_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("AIPODCASTER_API_KEY", "")

server = MCPServer(
    name="aipodcaster",
    version="1.0.0",
    instructions=(
        "Tools for the AiPodcaster post-production app. Typical flow: upload_recording → wait with get_job until stage is "
        "waiting_for_approval → optionally run_fact_check → approve_and_render → list outputs. Libraries hold reference documents "
        "used for fact checking; projects decide which libraries an episode uses."
    ),
)


def _client() -> httpx.Client:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return httpx.Client(base_url=API_URL, headers=headers, timeout=120)


def _call(method: str, path: str, **kwargs: Any) -> Any:
    with _client() as client:
        response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {detail}")
    if response.status_code == 204 or not response.content:
        return {"ok": True}
    return response.json()


def _compact_job(job: dict) -> dict:
    """Trim word-level data so tool results stay small."""
    out = {k: v for k, v in job.items() if k not in {"segments", "proposals"}}
    out["segment_count"] = len(job.get("segments", []))
    out["proposal_count"] = len(job.get("proposals", []))
    out["verification"] = {k: v for k, v in job.get("verification", {}).items() if k != "checks"} | {"flagged_claims": [c["claim"] for c in job.get("verification", {}).get("checks", []) if c.get("flagged") and not c.get("dismissed")]}
    return out


@server.tool(description="Health check of the AiPodcaster API and configured providers.")
def status() -> dict:
    return {"api": _call("GET", "/healthz"), "providers": _call("GET", "/v1/settings/providers")}


@server.tool(description="List episodes (jobs) with stage and progress.")
def list_jobs() -> list[dict]:
    return _call("GET", "/v1/jobs")


@server.tool(description="Get one episode. Set include_transcript=true to receive segments and proposals.")
def get_job(job_id: str, include_transcript: bool = False) -> dict:
    job = _call("GET", f"/v1/jobs/{job_id}")
    if include_transcript:
        job["segments"] = [{"id": s["id"], "start_ms": s["start_ms"], "text": s["text"]} for s in job["segments"]]
        job["proposals"] = [{k: p[k] for k in ("id", "kind", "start_ms", "end_ms", "text", "reason", "confidence", "accepted")} for p in job["proposals"]]
        return job
    return _compact_job(job)


@server.tool(description="Upload a local audio/video file and start analysis. Optionally attach it to a project (project_id).")
def upload_recording(file_path: str, project_id: str | None = None) -> dict:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise RuntimeError(f"File not found: {path}")
    with path.open("rb") as handle, _client() as client:
        response = client.post("/v1/jobs", files={"file": (path.name, handle)}, data={"project_id": project_id} if project_id else None, timeout=None)
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    return _compact_job(response.json())


@server.tool(description="Import an episode from a link: YouTube, Vimeo, podcast page or direct audio/video URL. Poll get_job until waiting_for_approval.")
def import_url(url: str, project_id: str | None = None) -> dict:
    return _compact_job(_call("POST", "/v1/jobs/url", json={"url": url, "project_id": project_id}))


@server.tool(description="Import a large recording or video that already exists on the server machine (absolute path) without uploading.")
def import_local_path(path: str, project_id: str | None = None) -> dict:
    return _compact_job(_call("POST", "/v1/jobs/local", json={"path": path, "project_id": project_id, "copy_file": True}))


@server.tool(description="Replace the text of transcript segments: edits = [{id, text}].")
def edit_transcript(job_id: str, edits: list[dict]) -> dict:
    return _compact_job(_call("PUT", f"/v1/jobs/{job_id}/transcript", json={"segments": edits}))


@server.tool(description="Approve the transcript and render the episode. decisions = [{id, accepted}] for proposals; omitted proposals keep their current state. voice_mode: original|synthetic.")
def approve_and_render(job_id: str, decisions: list[dict] | None = None, title: str = "", voice_mode: str = "original") -> dict:
    return _compact_job(_call("POST", f"/v1/jobs/{job_id}/approval", json={"decisions": decisions or [], "segments": [], "voice_mode": voice_mode, "title": title}))


@server.tool(description="Run a fact check on the transcript against the project's libraries and/or Wikipedia.")
def run_fact_check(job_id: str, use_libraries: bool = True, use_online: bool = False) -> dict:
    return _compact_job(_call("POST", f"/v1/jobs/{job_id}/verify", json={"use_libraries": use_libraries, "use_online": use_online}))


@server.tool(description="Return the full fact-check report (claims, verdicts, evidence) of an episode.")
def get_fact_check(job_id: str) -> dict:
    return _call("GET", f"/v1/jobs/{job_id}")["verification"]


@server.tool(description="List downloadable outputs of a finished episode with their URLs.")
def list_outputs(job_id: str) -> list[dict]:
    job = _call("GET", f"/v1/jobs/{job_id}")
    return [{**o, "url": f"{API_URL}/v1/jobs/{job_id}/outputs/{o['name']}"} for o in job.get("outputs", [])]


@server.tool(description="Download one output file of an episode to a local path.")
def download_output(job_id: str, name: str, destination: str) -> dict:
    target = Path(destination).expanduser()
    with _client() as client:
        response = client.get(f"/v1/jobs/{job_id}/outputs/{name}")
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    return {"saved": str(target), "bytes": len(response.content)}


@server.tool(description="List knowledge libraries.")
def list_libraries() -> list[dict]:
    return _call("GET", "/v1/libraries")


@server.tool(description="Create a knowledge library.")
def create_library(name: str, description: str = "") -> dict:
    return _call("POST", "/v1/libraries", json={"name": name, "description": description})


@server.tool(description="Add local documents (pdf, docx, epub, md, txt, html) to a library; they are indexed in the background.")
def add_documents(library_id: str, file_paths: list[str]) -> list[dict]:
    files = []
    handles = []
    try:
        for item in file_paths:
            path = Path(item).expanduser()
            if not path.is_file():
                raise RuntimeError(f"File not found: {path}")
            handle = path.open("rb")
            handles.append(handle)
            files.append(("files", (path.name, handle)))
        with _client() as client:
            response = client.post(f"/v1/libraries/{library_id}/documents", files=files, timeout=None)
    finally:
        for handle in handles:
            handle.close()
    if response.status_code >= 400:
        raise RuntimeError(response.text)
    return response.json()


@server.tool(description="Add a web page or online PDF to a library by URL.")
def add_url(library_id: str, url: str, name: str = "") -> dict:
    return _call("POST", f"/v1/libraries/{library_id}/documents/url", json={"url": url, "name": name})


@server.tool(description="Semantic search inside a library.")
def search_library(library_id: str, query: str, limit: int = 5) -> list[dict]:
    return _call("GET", f"/v1/libraries/{library_id}/search", params={"q": query, "limit": limit})


@server.tool(description="List projects (podcasts) and the libraries they use.")
def list_projects() -> list[dict]:
    return _call("GET", "/v1/projects")


@server.tool(description="Create a project that uses the given libraries and optionally inherits other projects' libraries.")
def create_project(name: str, library_ids: list[str] | None = None, linked_project_ids: list[str] | None = None, description: str = "", online_fact_check: bool = False) -> dict:
    return _call("POST", "/v1/projects", json={"name": name, "description": description, "library_ids": library_ids or [], "linked_project_ids": linked_project_ids or [], "online_fact_check": online_fact_check})


@server.tool(description="Show provider configuration (secrets masked) and which LLM/speech providers are available.")
def get_providers() -> dict:
    return {"settings": _call("GET", "/v1/settings"), "catalog": _call("GET", "/v1/providers/catalog")}


@server.tool(description="Check Ollama: running state, installed models, recommended model for this machine.")
def ollama_status() -> dict:
    return _call("GET", "/v1/providers/ollama/status")


@server.tool(description="Make Ollama the language model: start it if needed, choose the best model (or the given one), pull it if missing and warm it up.")
def ollama_setup(model: str | None = None) -> dict:
    return _call("POST", "/v1/providers/ollama/setup", json={"model": model, "start_server": True})


@server.tool(description="Send a tiny prompt to the configured language model and report latency.")
def test_language_model() -> dict:
    return _call("POST", "/v1/providers/llm/test")


def main() -> None:
    parser = argparse.ArgumentParser(description="AiPodcaster MCP server")
    parser.add_argument("--http", action="store_true", help="serve over streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--print-config", action="store_true", help="print an MCP client config snippet and exit")
    args = parser.parse_args()
    if args.print_config:
        snippet = {"mcpServers": {"aipodcaster": {"command": "python", "args": [str(Path(__file__).resolve())], "env": {"AIPODCASTER_URL": API_URL, "AIPODCASTER_API_KEY": API_KEY or "<key from Settings → API access>"}}}}
        print(json.dumps(snippet, indent=2))
        return
    if args.http:
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
