"""File-system backed job persistence with strict path handling.

Every job owns one directory under ``DATA_DIR/jobs/<uuid>``. Only the UUID is
ever used to build paths, never user supplied names.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from .config import DATA_DIR
from .schemas import JobSummary, ProcessingJob, utc_now

JOBS_DIR = DATA_DIR / "jobs"
SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
MAX_ASSET_NAME_LENGTH = 180
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".mov", ".wma", ".aiff", ".aif"}


def safe_asset_name(name: str) -> str:
    """Normalise an upload file name; reject path separators and odd input."""
    candidate = Path(name.replace("\\", "/")).name.strip()
    if not candidate or candidate != name.strip() or len(candidate) > MAX_ASSET_NAME_LENGTH:
        raise HTTPException(status_code=422, detail="Invalid asset name")
    cleaned = SAFE_NAME.sub("_", candidate).strip(" .")
    if not cleaned or cleaned.startswith("."):
        raise HTTPException(status_code=422, detail="Invalid asset name")
    if Path(cleaned).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Unsupported media type")
    return cleaned


def summarise_job(job: ProcessingJob) -> JobSummary:
    return JobSummary(
        id=job.id,
        project_id=job.project_id,
        asset_name=job.asset_name,
        display_name=job.display_name or job.show_notes.title or job.asset_name,
        source_kind=job.source_kind,
        archived=job.archived,
        order=job.order,
        tags=job.tags,
        stage=job.stage,
        progress=job.progress,
        message=job.message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        duration_ms=job.media.duration_ms,
        final_duration_ms=job.quality.final_duration_ms,
        word_count=sum(len(segment.text.split()) for segment in job.segments),
        proposal_count=len(job.proposals),
        accepted_edits=sum(1 for proposal in job.proposals if proposal.accepted),
        flagged_claims=sum(1 for check in job.verification.checks if check.flagged and not check.dismissed),
        output_count=len(job.outputs),
        published=sum(1 for record in job.publish_history if record.status == "success"),
        language=job.language,
    )


class JobStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.RLock()
        self._cache: dict[UUID, ProcessingJob] = {}

    def job_dir(self, job_id: UUID) -> Path:
        path = (self._root / str(job_id)).resolve()
        if path.parent != self._root.resolve():
            raise HTTPException(status_code=400, detail="Invalid job path")
        return path

    def output_dir(self, job_id: UUID) -> Path:
        return self.job_dir(job_id) / "output"

    def create(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            directory = self.job_dir(job.id)
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "output").mkdir()
            self._write(job)
            return job

    def save(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            job.updated_at = utc_now()
            self._write(job)
            return job

    def get(self, job_id: UUID) -> ProcessingJob:
        with self._lock:
            if job_id in self._cache:
                return self._cache[job_id].model_copy(deep=True)
            path = self.job_dir(job_id) / "job.json"
            if not path.exists():
                raise HTTPException(status_code=404, detail="Job not found")
            job = ProcessingJob.model_validate_json(path.read_text("utf-8"))
            self._cache[job_id] = job
            return job.model_copy(deep=True)

    def list(self) -> list[JobSummary]:
        summaries: list[JobSummary] = []
        if not self._root.exists():
            return summaries
        for child in self._root.iterdir():
            try:
                job = self.get(UUID(child.name))
            except (ValueError, HTTPException):
                continue
            summaries.append(summarise_job(job))
        return sorted(summaries, key=lambda item: (item.order, -item.created_at.timestamp()))

    def delete(self, job_id: UUID) -> None:
        with self._lock:
            directory = self.job_dir(job_id)
            if not directory.exists():
                raise HTTPException(status_code=404, detail="Job not found")
            self._cache.pop(job_id, None)
            shutil.rmtree(directory, ignore_errors=True)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            if self._root.exists():
                shutil.rmtree(self._root, ignore_errors=True)

    def _write(self, job: ProcessingJob) -> None:
        self._cache[job.id] = job.model_copy(deep=True)
        path = self.job_dir(job.id) / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job.model_dump(mode="json"), indent=2), "utf-8")
        tmp.replace(path)


job_store = JobStore(JOBS_DIR)
