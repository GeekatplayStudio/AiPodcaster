"""Import recordings from URLs (YouTube, Vimeo, podcast pages, direct media links)
and from large files already on this machine.

Downloads use yt-dlp, audio-only where the site offers separate streams, with
progress written back to the job so the UI can show it.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException

from ..config import MAX_UPLOAD_BYTES
from ..schemas import JobStage, ProcessingJob
from ..storage import ALLOWED_EXTENSIONS, JobStore, job_store, safe_asset_name

log = logging.getLogger("aipodcaster.remote")
PRIVATE_HOSTS = re.compile(r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.0\.0\.0|\[?::1\]?|172\.(1[6-9]|2\d|3[01])\.)", re.I)


class RemoteMediaError(RuntimeError):
    pass


def validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Only http(s) links are supported")
    if PRIVATE_HOSTS.match(parsed.hostname or ""):
        raise HTTPException(status_code=422, detail="Links to private or local addresses are not allowed")
    return parsed.geturl()


def probe_url(url: str) -> dict:
    """Resolve title, duration and uploader without downloading (used for naming)."""
    import yt_dlp

    options = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "socket_timeout": 30}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as error:  # noqa: BLE001 - yt-dlp raises many types
        raise RemoteMediaError(f"Could not read the link: {str(error)[:200]}") from error
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        info = entries[0] if entries else info
    return {"title": str(info.get("title") or "episode")[:150], "duration": float(info.get("duration") or 0), "uploader": str(info.get("uploader") or info.get("channel") or "")[:100], "extractor": str(info.get("extractor_key") or "")}


def download(url: str, target_dir: Path, progress) -> Path:  # noqa: ANN001 - callable(fraction, message)
    """Download the best audio stream (or the whole file for direct links) into target_dir."""
    import yt_dlp

    target_dir.mkdir(parents=True, exist_ok=True)
    template = str(target_dir / "download.%(ext)s")

    def hook(status: dict) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            done = status.get("downloaded_bytes") or 0
            if total and done > MAX_UPLOAD_BYTES:
                raise RemoteMediaError("Download exceeds the configured size limit")
            progress(done / total if total else 0.0, f"Downloading {status.get('_percent_str', '').strip()} {status.get('_speed_str', '').strip()}".strip())
        elif status.get("status") == "finished":
            progress(1.0, "Download finished, preparing audio")

    options = {
        "format": "bestaudio/best",
        "outtmpl": template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "max_filesize": MAX_UPLOAD_BYTES,
        "retries": 3,
        "socket_timeout": 30,
        "ffmpeg_location": shutil.which("ffmpeg"),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except RemoteMediaError:
        raise
    except Exception as error:  # noqa: BLE001
        raise RemoteMediaError(f"Download failed: {str(error)[:200]}") from error
    files = sorted(target_dir.glob("download.*"), key=lambda p: p.stat().st_size, reverse=True)
    if not files:
        raise RemoteMediaError("The link did not produce a media file")
    return files[0]


def run_download(job_id: UUID, url: str, store: JobStore = job_store) -> ProcessingJob:
    """Background step: fetch the media into the job directory, then hand over to analysis."""
    from .pipeline import run_analysis, source_path

    job = store.get(job_id)
    job.stage, job.progress, job.message = JobStage.INGEST, 1, "Connecting to link"
    store.save(job)

    def progress(fraction: float, message: str) -> None:
        current = store.get(job_id)
        current.progress, current.message = max(1, min(20, int(fraction * 20))), message
        store.save(current)

    try:
        file = download(url, store.job_dir(job_id) / "remote", progress)
        shutil.move(str(file), str(source_path(store, job_id)))
        shutil.rmtree(store.job_dir(job_id) / "remote", ignore_errors=True)
        job = store.get(job_id)
        job.media.size_bytes = source_path(store, job_id).stat().st_size
        store.save(job)
    except (RemoteMediaError, OSError) as error:
        job = store.get(job_id)
        job.stage, job.error, job.message = JobStage.FAILED, str(error)[:500], "Download failed"
        return store.save(job)
    return run_analysis(job_id, store)


def resolve_local_path(raw: str) -> Path:
    """Validate a path to a media file that already exists on this machine."""
    path = Path(raw.strip().strip('"')).expanduser()
    if not path.is_absolute():
        raise HTTPException(status_code=422, detail="Use an absolute path, for example D:\\Recordings\\show.mp4")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on this machine")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported media type; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the configured size limit (AIPODCASTER_MAX_UPLOAD_MB)")
    safe_asset_name(path.name)
    return path
