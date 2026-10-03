"""LangGraph orchestration of the episode pipeline with persistent checkpoints.

Graph::

    START ─┬─▶ download ─▶ ingest ─▶ transcribe ─▶ propose ─▶ ⏸ approval ─▶ render ─▶ END
           ├─▶ ingest  (file already present)
           └─▶ render  (re-render of an approved episode)

* Every node persists a checkpoint in ``data/checkpoints.sqlite`` (thread id =
  ``<job id>#<run>``), so a crash or restart resumes at the node that was
  running instead of starting over. Expensive transcription is never repeated
  because show-note generation failed.
* The human review is a real interrupt (``interrupt_before=["render"]``): the
  graph stops after ``propose`` and is resumed by the approval endpoint.
* Node bodies live in ``pipeline`` and ``remote_media``; this module only wires them.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from typing import TypedDict
from uuid import UUID

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from ..config import DATA_DIR
from ..schemas import JobStage, SourceKind
from ..storage import job_store
from . import pipeline, remote_media

log = logging.getLogger("aipodcaster.workflow")
CHECKPOINT_PATH = DATA_DIR / "checkpoints.sqlite"
PROCESSING = {JobStage.UPLOADED, JobStage.INGEST, JobStage.TRANSCRIBE, JobStage.PROPOSE_EDITS, JobStage.RENDER}
_lock = threading.Lock()
_graph = None


class PipelineState(TypedDict, total=False):
    job_id: str
    phase: str
    ok: bool


def _node(step):  # noqa: ANN001
    def run(state: PipelineState) -> PipelineState:
        return {"ok": bool(step(UUID(state["job_id"])))}

    run.__name__ = getattr(step, "__name__", "step")
    return run


def _route_start(state: PipelineState) -> str:
    if state.get("phase") == "render":
        return "render"
    job_id = UUID(state["job_id"])
    if not pipeline.source_path(job_store, job_id).exists() and job_store.get(job_id).source_url:
        return "download"
    return "ingest"


def _then(next_node: str):  # noqa: ANN001
    def route(state: PipelineState) -> str:
        return next_node if state.get("ok") else END

    return route


def build_graph(checkpointer) -> object:  # noqa: ANN001
    builder = StateGraph(PipelineState)
    builder.add_node("download", _node(remote_media.download_step))
    builder.add_node("ingest", _node(pipeline.ingest_step))
    builder.add_node("transcribe", _node(pipeline.transcribe_step))
    builder.add_node("propose", _node(pipeline.propose_step))
    builder.add_node("render", _node(pipeline.render_step))
    builder.add_conditional_edges(START, _route_start, ["download", "ingest", "render"])
    builder.add_conditional_edges("download", _then("ingest"), ["ingest", END])
    builder.add_conditional_edges("ingest", _then("transcribe"), ["transcribe", END])
    builder.add_conditional_edges("transcribe", _then("propose"), ["propose", END])
    builder.add_conditional_edges("propose", _then("render"), ["render", END])
    builder.add_edge("render", END)
    return builder.compile(checkpointer=checkpointer, interrupt_before=["render"])


def graph():
    global _graph
    with _lock:
        if _graph is None:
            CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
            _graph = build_graph(SqliteSaver(connection))
        return _graph


def _config(job_id: UUID, run: int) -> dict:
    return {"configurable": {"thread_id": f"{job_id}#{run}"}}


def paused_before_render(job_id: UUID, run: int) -> bool:
    state = graph().get_state(_config(job_id, run))
    return tuple(state.next) == ("render",)


def run(job_id: UUID, phase: str) -> None:
    """Execute (or resume) the workflow for a job. Blocking; called from a worker thread."""
    job = job_store.get(job_id)
    if phase == "render":
        if paused_before_render(job_id, job.pipeline_run):
            graph().invoke(None, _config(job_id, job.pipeline_run))
            return
        job.pipeline_run += 1
        job_store.save(job)
        config = _config(job_id, job.pipeline_run)
        graph().invoke({"job_id": str(job_id), "phase": "render"}, config)
        if paused_before_render(job_id, job.pipeline_run):
            graph().invoke(None, config)
        return
    job.pipeline_run += 1
    job_store.save(job)
    graph().invoke({"job_id": str(job_id), "phase": "analysis"}, _config(job_id, job.pipeline_run))


def resume(job_id: UUID) -> None:
    """Continue an interrupted run from its last checkpoint (or restart it when none exists)."""
    job = job_store.get(job_id)
    config = _config(job_id, job.pipeline_run)
    state = graph().get_state(config) if job.pipeline_run else None
    if state is not None and state.next:
        if tuple(state.next) == ("render",) and job.stage != JobStage.RENDER:
            return  # waiting for the user's approval
        log.info("Resuming %s at %s", job_id, state.next)
        graph().invoke(None, config)
        return
    run(job_id, "render" if job.stage == JobStage.RENDER else "analysis")


def resume_incomplete() -> list[UUID]:
    """Called at startup: pick up jobs that were processing when the server stopped."""
    resumed: list[UUID] = []
    for summary in job_store.list():
        if summary.stage not in PROCESSING or summary.source_kind == SourceKind.TEXT and summary.stage != JobStage.RENDER:
            continue
        if pipeline.is_active(summary.id):
            continue
        job = job_store.get(summary.id)
        job.message = "Resuming after restart"
        job_store.save(job)
        if pipeline.submit_resume(summary.id):
            resumed.append(summary.id)
    return resumed
