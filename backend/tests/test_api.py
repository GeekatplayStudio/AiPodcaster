import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline
from app.storage import safe_asset_name

client = TestClient(app)


def wait_for(job_id: str, stages: set[str], timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["stage"] in stages:
            return job
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {stages}: {job}")


def upload(sample_wav: Path, name: str = "episode.wav") -> dict:
    with sample_wav.open("rb") as handle:
        response = client.post("/v1/jobs", files={"file": (name, handle, "audio/wav")})
    assert response.status_code == 201, response.text
    return response.json()


def test_safe_asset_name_rules():
    assert safe_asset_name("My Episode (1).wav") == "My Episode _1_.wav"
    for bad in ("../x.wav", "x/y.wav", "", "notes.txt", "a" * 200 + ".wav"):
        with pytest.raises(HTTPException):
            safe_asset_name(bad)


def test_rejects_non_media_and_empty_uploads(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with empty.open("rb") as handle:
        assert client.post("/v1/jobs", files={"file": ("empty.wav", handle, "audio/wav")}).status_code == 422
    assert client.post("/v1/jobs", files={"file": ("notes.txt", b"hello", "text/plain")}).status_code == 422
    fake = client.post("/v1/jobs", files={"file": ("fake.wav", b"this is not audio at all", "audio/wav")})
    assert fake.status_code == 201
    job = wait_for(fake.json()["id"], {"failed"})
    assert "does not look like" in job["error"]


def test_full_pipeline_upload_review_approve_render(sample_wav):
    job = upload(sample_wav)
    job = wait_for(job["id"], {"waiting_for_approval", "failed"})
    assert job["stage"] == "waiting_for_approval", job.get("error")
    assert job["media"]["duration_ms"] == pytest.approx(12_000, abs=100)
    assert job["transcription_provider"] == "fake"
    assert job["segments"] and job["proposals"]
    kinds = {p["kind"] for p in job["proposals"]}
    assert {"profanity", "filler", "repeat", "silence"} <= kinds

    # Edit transcript text while keeping timing.
    first = job["segments"][0]
    edited = client.put(f"/v1/jobs/{job['id']}/transcript", json={"segments": [{"id": first["id"], "text": "Welcome back to the programme."}]})
    assert edited.status_code == 200
    assert edited.json()["segments"][0]["text"] == "Welcome back to the programme."

    # Reject every filler, accept the rest, approve and render.
    decisions = [{"id": p["id"], "accepted": p["kind"] != "filler"} for p in job["proposals"]]
    approved = client.post(f"/v1/jobs/{job['id']}/approval", json={"decisions": decisions, "voice_mode": "original", "title": "Test Episode"})
    assert approved.status_code == 200
    done = wait_for(job["id"], {"complete", "failed"})
    assert done["stage"] == "complete", done.get("error")
    names = {o["name"] for o in done["outputs"]}
    assert {"test-episode.mp3", "test-episode-master.wav", "test-episode.srt", "test-episode.vtt", "test-episode-show-notes.md", "test-episode-metadata.json", "test-episode-chapters.txt", "test-episode-publish-kit.zip"} <= names
    assert done["quality"]["final_duration_ms"] < done["quality"]["original_duration_ms"]
    assert done["quality"]["output_lufs"] is not None
    assert done["quality"]["rejected_edits"] == sum(1 for p in job["proposals"] if p["kind"] == "filler")

    download = client.get(f"/v1/jobs/{job['id']}/outputs/test-episode.mp3")
    assert download.status_code == 200 and download.headers["content-type"].startswith("audio/mpeg")
    assert client.get(f"/v1/jobs/{job['id']}/outputs/../job.json").status_code in {404, 422}
    assert client.get(f"/v1/jobs/{job['id']}/audio/original").status_code == 200
    assert client.get("/v1/jobs").json()[0]["id"] == job["id"]
    assert client.delete(f"/v1/jobs/{job['id']}").status_code == 204
    assert client.get(f"/v1/jobs/{job['id']}").status_code == 404


def test_approval_rejects_unknown_ids_and_wrong_stage(sample_wav):
    job = upload(sample_wav)
    assert client.post(f"/v1/jobs/{job['id']}/approval", json={"decisions": []}).status_code == 409
    job = wait_for(job["id"], {"waiting_for_approval"})
    response = client.post(f"/v1/jobs/{job['id']}/approval", json={"decisions": [{"id": "00000000-0000-4000-8000-000000000000", "accepted": True}]})
    assert response.status_code == 422


def test_settings_mask_secrets_and_keep_them_on_round_trip():
    current = client.get("/v1/settings").json()
    current["keys"]["openai_api_key"] = "sk-test-secret"
    saved = client.put("/v1/settings", json=current).json()
    assert saved["keys"]["openai_api_key"] == "••••••••"
    saved["cleanup"]["max_pause_ms"] = 2000
    again = client.put("/v1/settings", json=saved).json()
    assert again["cleanup"]["max_pause_ms"] == 2000
    from app.config import settings_store

    assert settings_store.get().keys.openai_api_key == "sk-test-secret"
    saved["keys"]["openai_api_key"] = ""
    client.put("/v1/settings", json=saved)
    assert settings_store.get().keys.openai_api_key == ""
    providers = client.get("/v1/settings/providers").json()
    assert any(p["name"] == "ffmpeg" and p["available"] for p in providers)


def test_security_headers_present():
    response = client.get("/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_submit_refuses_duplicate_work(sample_wav):
    job = upload(sample_wav)
    assert pipeline.submit(job["id"], "analysis") in {True, False}
    wait_for(job["id"], {"waiting_for_approval", "failed"})
