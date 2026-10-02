"""Background runner for transcript fact checking."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException

from ..config import AppSettings, settings_store
from ..rag.store import library_store, project_store
from ..rag.verify import verify_job
from ..schemas import ProcessingJob, VerificationStatus, VerifyRequest
from ..storage import JobStore, job_store

log = logging.getLogger("aipodcaster.verification")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="verify")
_active: set[UUID] = set()
_lock = threading.Lock()


def resolve_libraries(job: ProcessingJob, request: VerifyRequest) -> list[UUID]:
    if not request.use_libraries:
        return []
    if request.library_ids is not None:
        for library_id in request.library_ids:
            library_store.get(library_id)
        return list(dict.fromkeys(request.library_ids))
    if job.project_id is None:
        return []
    try:
        project = project_store.get(job.project_id)
    except HTTPException:
        return []
    return project_store.resolve_library_ids(project)


def run(job_id: UUID, library_ids: list[UUID], use_online: bool, store: JobStore = job_store, settings: AppSettings | None = None) -> ProcessingJob:
    settings = settings or settings_store.get()
    job = store.get(job_id)
    try:
        libraries = []
        for library_id in library_ids:
            try:
                libraries.append(library_store.get(library_id))
            except HTTPException:
                continue
        job.verification = verify_job(job, libraries, use_online and settings.fact_check.online_enabled, settings)
    except Exception as error:  # noqa: BLE001 - report instead of crashing the worker
        log.exception("Fact check failed for %s", job_id)
        job.verification.status = VerificationStatus.FAILED
        job.verification.error = str(error)[:500]
        job.verification.message = "Fact check failed"
        job.verification.finished_at = datetime.now(UTC)
    return store.save(job)


def submit(job_id: UUID, library_ids: list[UUID], use_online: bool) -> bool:
    with _lock:
        if job_id in _active:
            return False
        _active.add(job_id)

    def task() -> None:
        try:
            run(job_id, library_ids, use_online)
        finally:
            with _lock:
                _active.discard(job_id)

    _executor.submit(task)
    return True


def is_active(job_id: UUID) -> bool:
    with _lock:
        return job_id in _active
