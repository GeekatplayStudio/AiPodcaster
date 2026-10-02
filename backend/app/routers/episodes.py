"""Episode management: text/transcript ingestion, metadata, ordering, bulk actions, stats."""
from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ..config import ALLOW_LOCAL_IMPORT, settings_store
from ..rag.parsing import ALLOWED_DOCUMENT_EXTENSIONS, ParseError, extract_text
from ..rag.store import project_store
from ..schemas import BulkRequest, JobMetaUpdate, JobStage, JobSummary, LocalPathImport, ProcessingJob, ReorderRequest, SourceKind, TextIngest, UrlImport, VoiceMode
from ..services import analysis, llm, pipeline, remote_media, stats, text_ingest
from ..storage import SAFE_NAME, job_store, summarise_job

router = APIRouter(prefix="/v1/jobs", tags=["episodes"])
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".srt", ".vtt", ".pdf", ".docx", ".html", ".htm", ".rtf", ".json", ".csv", ".epub"}
MAX_TEXT_BYTES = 50 * 1024 * 1024


def _create_text_job(text: str, name: str, project_id: UUID | None, wpm: int) -> ProcessingJob:
    if project_id is not None:
        project_store.get(project_id)
    detected = text_ingest.build_segments(text, wpm)
    if not detected.segments:
        raise HTTPException(status_code=422, detail="No readable sentences were found in the text")
    settings = settings_store.get()
    job = ProcessingJob(asset_name=name, project_id=project_id, source_kind=SourceKind.TEXT, voice_mode=VoiceMode.SYNTHETIC, message=f"Imported {detected.format} text")
    job.segments, job.language = detected.segments, settings.transcription.language
    job.media.duration_ms = detected.estimated_duration_ms
    job.media.codec, job.media.channels, job.media.sample_rate = f"text/{detected.format}", 0, 0
    job.quality.original_duration_ms = detected.estimated_duration_ms
    job.proposals = analysis.build_proposals(job.segments, [], settings.cleanup, detected.estimated_duration_ms)
    job.show_notes = llm.generate_show_notes(settings, job.segments, Path(name).stem.replace("_", " ").replace("-", " ").title())
    job.stage, job.progress = JobStage.WAITING_FOR_APPROVAL, 100
    job.message = f"{detected.format} transcript · {detected.word_count} words · {len(job.proposals)} suggestions"
    job_store.create(job)
    (job_store.job_dir(job.id) / "source.txt").write_text(text, "utf-8")
    return job


@router.post("/text", response_model=ProcessingJob, status_code=status.HTTP_201_CREATED)
async def create_from_text(body: TextIngest) -> ProcessingJob:
    """Create an episode from pasted text (transcript, script, article)."""
    name = SAFE_NAME.sub("_", body.name).strip(" .") or "Pasted transcript"
    return _create_text_job(body.text, name[:180], body.project_id, body.words_per_minute)


@router.post("/text/upload", response_model=ProcessingJob, status_code=status.HTTP_201_CREATED)
async def create_from_text_file(file: UploadFile, project_id: UUID | None = None, words_per_minute: int = 150) -> ProcessingJob:
    """Create an episode from a text-like document: TXT, MD, SRT, VTT, PDF, DOCX, HTML, EPUB."""
    name = Path((file.filename or "").replace("\\", "/")).name.strip()
    cleaned = SAFE_NAME.sub("_", name).strip(" .")
    suffix = Path(cleaned).suffix.lower()
    if not cleaned or suffix not in TEXT_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported text document; allowed: {', '.join(sorted(TEXT_EXTENSIONS))}")
    data = await file.read(MAX_TEXT_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(data) > MAX_TEXT_BYTES:
        raise HTTPException(status_code=413, detail="Text document is too large")
    tmp_dir = job_store.job_dir(UUID(int=0)).parent / "_incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{abs(hash(cleaned))}{suffix}"
    tmp.write_bytes(data)
    try:
        text = extract_text(tmp, cleaned) if suffix in ALLOWED_DOCUMENT_EXTENSIONS else data.decode("utf-8", errors="replace")
    except ParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        tmp.unlink(missing_ok=True)
    return _create_text_job(text, cleaned[:180], project_id, max(80, min(words_per_minute, 260)))


_downloads = ThreadPoolExecutor(max_workers=2, thread_name_prefix="download")


@router.post("/url", response_model=ProcessingJob, status_code=status.HTTP_202_ACCEPTED)
async def create_from_url(body: UrlImport) -> ProcessingJob:
    """Import audio from YouTube, Vimeo, podcast pages or direct media links (yt-dlp)."""
    url = remote_media.validate_url(body.url)
    if body.project_id is not None:
        project_store.get(body.project_id)
    try:
        info = await run_in_threadpool(remote_media.probe_url, url)
    except remote_media.RemoteMediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    name = SAFE_NAME.sub("_", info["title"]).strip(" .")[:150] or "remote-episode"
    job = ProcessingJob(asset_name=f"{name}.m4a", display_name=info["title"], project_id=body.project_id, source_url=url, message=f"Queued download from {info['extractor'] or 'link'}")
    if info["uploader"]:
        job.tags = [info["uploader"][:40]]
    job_store.create(job)
    _downloads.submit(remote_media.run_download, job.id, url)
    return job_store.get(job.id)


@router.post("/local", response_model=ProcessingJob, status_code=status.HTTP_201_CREATED)
async def create_from_local_path(body: LocalPathImport) -> ProcessingJob:
    """Import a large recording or video that already exists on this machine without uploading it."""
    if not ALLOW_LOCAL_IMPORT:
        raise HTTPException(status_code=403, detail="Local path import is disabled (AIPODCASTER_ALLOW_LOCAL_IMPORT=0)")
    path = remote_media.resolve_local_path(body.path)
    if body.project_id is not None:
        project_store.get(body.project_id)
    job = job_store.create(ProcessingJob(asset_name=path.name, project_id=body.project_id, message="Importing from local path"))
    target = pipeline.source_path(job_store, job.id)
    await run_in_threadpool(shutil.copy2 if body.copy_file else _link_or_copy, str(path), str(target))
    job.media.size_bytes = target.stat().st_size
    job.message = "Queued for analysis"
    job_store.save(job)
    pipeline.submit(job.id, "analysis")
    return job_store.get(job.id)


def _link_or_copy(source: str, target: str) -> None:
    try:
        Path(target).hardlink_to(source)
    except OSError:
        shutil.copy2(source, target)


@router.patch("/{job_id}/meta", response_model=ProcessingJob)
async def update_meta(job_id: UUID, body: JobMetaUpdate) -> ProcessingJob:
    job = job_store.get(job_id)
    if body.display_name is not None:
        job.display_name = " ".join(body.display_name.split())[:200]
    if body.archived is not None:
        job.archived = body.archived
    if body.clear_project:
        job.project_id = None
    elif body.project_id is not None:
        project_store.get(body.project_id)
        job.project_id = body.project_id
    if body.tags is not None:
        job.tags = [tag.strip()[:40] for tag in body.tags if tag.strip()][:30]
    if body.notes is not None:
        job.notes = body.notes
    return job_store.save(job)


@router.post("/reorder", response_model=list[JobSummary])
async def reorder(body: ReorderRequest) -> list[JobSummary]:
    """Persist a manual order; ids not listed keep their relative position after the listed ones."""
    position = {job_id: index for index, job_id in enumerate(body.ids)}
    for summary in job_store.list():
        job = job_store.get(summary.id)
        new_order = position.get(job.id, len(position) + job.order)
        if job.order != new_order:
            job.order = new_order
            job_store.save(job)
    return job_store.list()


@router.post("/bulk", response_model=list[JobSummary])
async def bulk(body: BulkRequest) -> list[JobSummary]:
    for job_id in body.ids:
        if body.action == "delete":
            if pipeline.is_active(job_id):
                raise HTTPException(status_code=409, detail=f"Episode {job_id} is still processing")
            job_store.delete(job_id)
            continue
        job = job_store.get(job_id)
        job.archived = body.action == "archive"
        job_store.save(job)
    return job_store.list()


@router.get("/{job_id}/stats")
async def job_stats(job_id: UUID) -> dict:
    return stats.compute_stats(job_store.get(job_id))


@router.get("/{job_id}/summary", response_model=JobSummary)
async def job_summary(job_id: UUID) -> JobSummary:
    return summarise_job(job_store.get(job_id))
