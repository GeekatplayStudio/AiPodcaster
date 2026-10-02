"""Job lifecycle endpoints: upload, status, transcript edits, approval, outputs."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..config import MAX_UPLOAD_BYTES
from ..rag.store import project_store
from ..schemas import ApprovalRequest, FactCheckDecision, JobStage, JobSummary, ProcessingJob, TranscriptUpdate, VerificationStatus, VerifyRequest
from ..services import pipeline, verification
from ..storage import job_store, safe_asset_name

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])
PROJECT_FORM = Form(default=None)
CHUNK = 1024 * 1024


@router.get("", response_model=list[JobSummary])
async def list_jobs(include_archived: bool = False, project_id: UUID | None = None, q: str | None = None) -> list[JobSummary]:
    items = job_store.list()
    if not include_archived:
        items = [item for item in items if not item.archived]
    if project_id is not None:
        items = [item for item in items if item.project_id == project_id]
    if q:
        needle = q.strip().lower()
        items = [item for item in items if needle in item.display_name.lower() or needle in item.asset_name.lower() or any(needle in tag.lower() for tag in item.tags)]
    return items


@router.post("", response_model=ProcessingJob, status_code=status.HTTP_201_CREATED)
async def create_job(file: UploadFile, project_id: UUID | None = PROJECT_FORM) -> ProcessingJob:
    """Accept a raw recording and queue analysis."""
    name = safe_asset_name(file.filename or "")
    if project_id is not None:
        project_store.get(project_id)
    job = job_store.create(ProcessingJob(asset_name=name, project_id=project_id, message="Uploading"))
    target = pipeline.source_path(job_store, job.id)
    written = 0
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(CHUNK):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the upload size limit")
                handle.write(chunk)
    except HTTPException:
        job_store.delete(job.id)
        raise
    finally:
        await file.close()
    if written == 0:
        job_store.delete(job.id)
        raise HTTPException(status_code=422, detail="The uploaded file is empty")
    job.media.size_bytes = written
    job.message = "Queued for analysis"
    job_store.save(job)
    pipeline.submit(job.id, "analysis")
    return job_store.get(job.id)


@router.get("/{job_id}", response_model=ProcessingJob)
async def get_job(job_id: UUID) -> ProcessingJob:
    return job_store.get(job_id)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: UUID) -> None:
    if pipeline.is_active(job_id):
        raise HTTPException(status_code=409, detail="Job is still processing")
    job_store.delete(job_id)


@router.post("/{job_id}/reanalyze", response_model=ProcessingJob)
async def reanalyze(job_id: UUID) -> ProcessingJob:
    job = job_store.get(job_id)
    if job.stage in {JobStage.INGEST, JobStage.TRANSCRIBE, JobStage.PROPOSE_EDITS, JobStage.RENDER} and pipeline.is_active(job_id):
        raise HTTPException(status_code=409, detail="Job is still processing")
    job.stage, job.progress, job.error, job.outputs = JobStage.UPLOADED, 0, None, []
    job_store.save(job)
    pipeline.submit(job.id, "analysis")
    return job_store.get(job.id)


@router.put("/{job_id}/transcript", response_model=ProcessingJob)
async def update_transcript(job_id: UUID, update: TranscriptUpdate) -> ProcessingJob:
    job = job_store.get(job_id)
    _require_review_stage(job)
    _apply_segment_edits(job, update.segments)
    return job_store.save(job)


@router.post("/{job_id}/approval", response_model=ProcessingJob)
async def approve_job(job_id: UUID, request: ApprovalRequest) -> ProcessingJob:
    job = job_store.get(job_id)
    _require_review_stage(job)
    valid = {proposal.id: proposal for proposal in job.proposals}
    unknown = [d.id for d in request.decisions if d.id not in valid]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown proposal IDs: {len(unknown)}")
    for decision in request.decisions:
        valid[decision.id].accepted = decision.accepted
    _apply_segment_edits(job, request.segments)
    if request.title.strip():
        job.show_notes.title = request.title.strip()
    job.voice_mode = request.voice_mode
    job.stage, job.progress, job.message, job.error = JobStage.RENDER, 0, "Queued for render", None
    job_store.save(job)
    pipeline.submit(job.id, "render")
    return job_store.get(job.id)


@router.put("/{job_id}/project", response_model=ProcessingJob)
async def set_project(job_id: UUID, project_id: UUID | None = None) -> ProcessingJob:
    job = job_store.get(job_id)
    if project_id is not None:
        project_store.get(project_id)
    job.project_id = project_id
    return job_store.save(job)


@router.post("/{job_id}/verify", response_model=ProcessingJob, status_code=status.HTTP_202_ACCEPTED)
async def verify(job_id: UUID, request: VerifyRequest) -> ProcessingJob:
    """Fact-check the transcript against project libraries and/or online sources."""
    job = job_store.get(job_id)
    if not job.segments:
        raise HTTPException(status_code=409, detail="Transcribe the recording before fact checking")
    if job.verification.status == VerificationStatus.RUNNING and verification.is_active(job_id):
        raise HTTPException(status_code=409, detail="Fact check already running")
    library_ids = verification.resolve_libraries(job, request)
    if not library_ids and not request.use_online:
        raise HTTPException(status_code=422, detail="Select at least one library (via the project) or enable online checking")
    job.verification.status, job.verification.message, job.verification.error = VerificationStatus.RUNNING, "Queued", None
    job_store.save(job)
    verification.submit(job.id, library_ids, request.use_online)
    return job_store.get(job.id)


@router.put("/{job_id}/verify/decisions", response_model=ProcessingJob)
async def fact_check_decisions(job_id: UUID, decisions: list[FactCheckDecision]) -> ProcessingJob:
    job = job_store.get(job_id)
    by_id = {c.id: c for c in job.verification.checks}
    for decision in decisions:
        check = by_id.get(decision.id)
        if check is None:
            raise HTTPException(status_code=422, detail="Unknown fact check")
        check.dismissed = decision.dismissed
    job.verification.flagged = sum(1 for c in job.verification.checks if c.flagged and not c.dismissed)
    return job_store.save(job)


@router.get("/{job_id}/audio/original")
async def original_audio(job_id: UUID) -> FileResponse:
    job_store.get(job_id)
    path = pipeline.canonical_wav(job_store, job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not ready")
    return FileResponse(path, media_type="audio/wav", filename="original.wav")


@router.get("/{job_id}/outputs/{name}")
async def download_output(job_id: UUID, name: str) -> FileResponse:
    job = job_store.get(job_id)
    output = next((item for item in job.outputs if item.name == name), None)
    if output is None or Path(name).name != name:
        raise HTTPException(status_code=404, detail="Output not found")
    path = job_store.output_dir(job_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output not found")
    return FileResponse(path, media_type=output.content_type, filename=name)


def _require_review_stage(job: ProcessingJob) -> None:
    if job.stage not in {JobStage.WAITING_FOR_APPROVAL, JobStage.COMPLETE, JobStage.FAILED}:
        raise HTTPException(status_code=409, detail="Job is not ready for review")
    if not job.segments:
        raise HTTPException(status_code=409, detail="Job has no transcript to review")


def _apply_segment_edits(job: ProcessingJob, edits) -> None:
    by_id = {segment.id: segment for segment in job.segments}
    for edit in edits:
        segment = by_id.get(edit.id)
        if segment is None:
            raise HTTPException(status_code=422, detail=f"Unknown segment {edit.id}")
        text = " ".join(edit.text.split())
        if text != segment.text:
            segment.text = text
            segment.words = _reflow_words(segment, text)
            job.text_edits += 1


def _reflow_words(segment, text: str):
    """Keep word timing when the user edits text; distribute evenly when counts differ."""
    tokens = text.split()
    if not tokens:
        return []
    if len(tokens) == len(segment.words):
        return [word.model_copy(update={"text": token}) for word, token in zip(segment.words, tokens, strict=True)]
    span = max(segment.end_ms - segment.start_ms, len(tokens))
    step = span / len(tokens)
    from ..schemas import Word

    return [Word(text=token, start_ms=int(segment.start_ms + i * step), end_ms=int(segment.start_ms + (i + 1) * step)) for i, token in enumerate(tokens)]
