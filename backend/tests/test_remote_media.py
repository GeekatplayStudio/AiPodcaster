import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services import remote_media

client = TestClient(app)


def wait_stage(job_id: str, stages: set[str], timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["stage"] in stages:
            return job
        time.sleep(0.2)
    raise AssertionError(f"timed out: {job}")


def test_url_validation_blocks_private_and_non_http():
    assert remote_media.validate_url(" https://www.youtube.com/watch?v=abc ") == "https://www.youtube.com/watch?v=abc"
    for bad in ("ftp://x/y", "http://localhost:8000/x", "http://192.168.1.5/a.mp3", "http://127.0.0.1/a", "notaurl"):
        with pytest.raises(HTTPException):
            remote_media.validate_url(bad)


def test_local_path_import_processes_files_without_upload(sample_wav: Path):
    assert client.post("/v1/jobs/local", json={"path": str(sample_wav.with_name("nope.wav"))}).status_code == 404
    assert client.post("/v1/jobs/local", json={"path": "recordings/show.wav"}).status_code == 422
    created = client.post("/v1/jobs/local", json={"path": str(sample_wav)})
    assert created.status_code == 201, created.text
    job = wait_stage(created.json()["id"], {"waiting_for_approval", "failed"})
    assert job["stage"] == "waiting_for_approval", job.get("error")
    assert sample_wav.exists()


def test_url_import_downloads_then_analyses(sample_wav: Path, monkeypatch):
    monkeypatch.setattr(remote_media, "probe_url", lambda url: {"title": "Deep Focus — Episode 14", "duration": 12.0, "uploader": "Geekatplay", "extractor": "Youtube"})

    def fake_download(url, target_dir, progress):
        progress(0.5, "Downloading 50%")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "download.wav"
        target.write_bytes(sample_wav.read_bytes())
        progress(1.0, "Download finished")
        return target

    monkeypatch.setattr(remote_media, "download", fake_download)
    accepted = client.post("/v1/jobs/url", json={"url": "https://www.youtube.com/watch?v=demo"})
    assert accepted.status_code == 202, accepted.text
    job = accepted.json()
    assert job["source_url"] == "https://www.youtube.com/watch?v=demo" and job["display_name"] == "Deep Focus — Episode 14" and job["tags"] == ["Geekatplay"]
    job = wait_stage(job["id"], {"waiting_for_approval", "failed"})
    assert job["stage"] == "waiting_for_approval", job.get("error")
    assert job["media"]["duration_ms"] > 0 and job["segments"]


def test_url_import_reports_download_failure(monkeypatch):
    monkeypatch.setattr(remote_media, "probe_url", lambda url: {"title": "x", "duration": 0, "uploader": "", "extractor": ""})

    def failing(url, target_dir, progress):
        raise remote_media.RemoteMediaError("Video unavailable")

    monkeypatch.setattr(remote_media, "download", failing)
    job = client.post("/v1/jobs/url", json={"url": "https://example.com/gone"}).json()
    failed = wait_stage(job["id"], {"failed"}, timeout=30)
    assert "Video unavailable" in failed["error"]

    def bad_probe(url):
        raise remote_media.RemoteMediaError("Unsupported URL")

    monkeypatch.setattr(remote_media, "probe_url", bad_probe)
    assert client.post("/v1/jobs/url", json={"url": "https://example.com/unknown"}).status_code == 422
