"""Publish kit, thumbnails, hosting targets and publishing actions."""
from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..config import settings_store
from ..publishing import connectors, kit
from ..publishing.schemas import CATALOG, PublishRequest, PublishTargetUpsert
from ..publishing.store import target_store
from ..schemas import ProcessingJob, PublishKit, PublishRecord
from ..storage import job_store

router = APIRouter(tags=["publishing"])
API_URL = os.environ.get("AIPODCASTER_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


class ThumbnailRequest(BaseModel):
    prompt: str = Field(default="", max_length=1_500)
    size: str = Field(default="square", pattern="^(square|youtube)$")


@router.get("/v1/publish/catalog")
async def catalog() -> list[dict]:
    return [asdict(kind) for kind in CATALOG]


@router.get("/v1/publish/targets")
async def list_targets() -> list[dict]:
    return [target.masked() for target in target_store.list()]


@router.post("/v1/publish/targets", status_code=status.HTTP_201_CREATED)
async def create_target(body: PublishTargetUpsert) -> dict:
    return target_store.create(body).masked()


@router.put("/v1/publish/targets/{target_id}")
async def update_target(target_id: UUID, body: PublishTargetUpsert) -> dict:
    return target_store.update(target_id, body).masked()


@router.delete("/v1/publish/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: UUID) -> None:
    target_store.delete(target_id)


@router.post("/v1/jobs/{job_id}/kit/generate", response_model=ProcessingJob)
async def generate_kit(job_id: UUID) -> ProcessingJob:
    job = job_store.get(job_id)
    if not job.segments:
        raise HTTPException(status_code=409, detail="Transcribe or import text first")
    generated = await run_in_threadpool(kit.generate_kit, settings_store.get(), job)
    generated.thumbnail_file = job.publish_kit.thumbnail_file
    generated.episode_number, generated.season_number, generated.explicit = job.publish_kit.episode_number, job.publish_kit.season_number, job.publish_kit.explicit
    job.publish_kit = generated
    return job_store.save(job)


@router.put("/v1/jobs/{job_id}/kit", response_model=ProcessingJob)
async def update_kit(job_id: UUID, body: PublishKit) -> ProcessingJob:
    job = job_store.get(job_id)
    body.thumbnail_file = job.publish_kit.thumbnail_file
    body.generated_by = body.generated_by or job.publish_kit.generated_by
    body.updated_at = datetime.now(UTC)
    job.publish_kit = body
    return job_store.save(job)


@router.post("/v1/jobs/{job_id}/kit/thumbnail", response_model=ProcessingJob)
async def make_thumbnail(job_id: UUID, body: ThumbnailRequest) -> ProcessingJob:
    job = job_store.get(job_id)
    prompt = body.prompt.strip() or job.publish_kit.thumbnail_prompt or kit.heuristic_kit(job).thumbnail_prompt
    name = f"thumbnail-{body.size}.png"
    target = job_store.output_dir(job_id) / name
    target.parent.mkdir(exist_ok=True)
    generator = await run_in_threadpool(kit.generate_thumbnail, settings_store.get(), job, prompt, target, body.size)
    job.publish_kit.thumbnail_prompt = prompt
    job.publish_kit.thumbnail_file = name
    job.publish_kit.generated_by = job.publish_kit.generated_by or "heuristic"
    _register_output(job, name, f"Thumbnail ({body.size}, {generator})", "image/png")
    return job_store.save(job)


@router.post("/v1/jobs/{job_id}/kit/thumbnail/upload", response_model=ProcessingJob)
async def upload_thumbnail(job_id: UUID, file: UploadFile) -> ProcessingJob:
    job = job_store.get(job_id)
    data = await file.read(15 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 15 * 1024 * 1024 or not data:
        raise HTTPException(status_code=413, detail="Image must be 1 byte to 15 MB")
    if not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
        raise HTTPException(status_code=422, detail="Only PNG or JPEG images are accepted")
    name = "thumbnail-custom.png" if data.startswith(b"\x89PNG") else "thumbnail-custom.jpg"
    target = job_store.output_dir(job_id) / name
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(data)
    job.publish_kit.thumbnail_file = name
    _register_output(job, name, "Thumbnail (uploaded)", "image/png" if name.endswith("png") else "image/jpeg")
    return job_store.save(job)


@router.get("/v1/jobs/{job_id}/kit/thumbnail")
async def get_thumbnail(job_id: UUID) -> FileResponse:
    job = job_store.get(job_id)
    if not job.publish_kit.thumbnail_file:
        raise HTTPException(status_code=404, detail="No thumbnail yet")
    path = job_store.output_dir(job_id) / job.publish_kit.thumbnail_file
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg")


@router.get("/v1/jobs/{job_id}/publish/package")
async def download_package(job_id: UUID) -> StreamingResponse:
    """Zip with audio, thumbnail, manifest and per-service text files for manual uploads."""
    job = job_store.get(job_id)
    manifest = connectors.build_manifest(job, API_URL)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("description.txt", job.publish_kit.long_description or job.show_notes.summary)
        archive.writestr("short-description.txt", job.publish_kit.short_description)
        archive.writestr("youtube-description.txt", job.publish_kit.youtube_description)
        archive.writestr("hashtags.txt", " ".join(f"#{h}" for h in job.publish_kit.hashtags))
        for network, post in job.publish_kit.social_posts.items():
            archive.writestr(f"social-{network}.txt", post)
        for output in job.outputs:
            path = job_store.output_dir(job_id) / output.name
            if path.exists() and not output.name.endswith(".zip"):
                archive.write(path, arcname=output.name)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{job.id}-publish-package.zip"'})


@router.post("/v1/jobs/{job_id}/publish", response_model=ProcessingJob)
async def publish_episode(job_id: UUID, body: PublishRequest) -> ProcessingJob:
    job = job_store.get(job_id)
    target = target_store.get(body.target_id)
    if not target.enabled:
        raise HTTPException(status_code=409, detail="Target is disabled")
    mp3 = next((o for o in job.outputs if o.content_type == "audio/mpeg"), None)
    if mp3 is None and connectors.kind_by_id(target.kind).mode == "api":
        raise HTTPException(status_code=409, detail="Produce the episode before publishing")
    package = connectors.Package(
        audio=job_store.output_dir(job_id) / mp3.name if mp3 else None,
        thumbnail=job_store.output_dir(job_id) / job.publish_kit.thumbnail_file if job.publish_kit.thumbnail_file else None,
        manifest=connectors.build_manifest(job, API_URL),
    )
    record = PublishRecord(target_id=target.id, target_name=target.name, target_kind=target.kind)
    try:
        record.status, record.message, record.url = await run_in_threadpool(connectors.publish, target, job, package)
    except (connectors.PublishError, OSError, KeyError) as error:
        record.status, record.message = "failed", str(error)[:500]
    job.publish_history.insert(0, record)
    job.publish_history = job.publish_history[:50]
    target_store.record_result(target.id, f"{record.status}: {record.message}")
    return job_store.save(job)


def _register_output(job: ProcessingJob, name: str, label: str, content_type: str) -> None:
    from ..schemas import OutputFile

    path = job_store.output_dir(job.id) / name
    job.outputs = [o for o in job.outputs if o.name != name]
    job.outputs.append(OutputFile(name=name, label=label, size_bytes=path.stat().st_size, content_type=content_type))
