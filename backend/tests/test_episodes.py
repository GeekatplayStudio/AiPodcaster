import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import text_ingest

client = TestClient(app)

SRT = """1
00:00:01,000 --> 00:00:04,000
Welcome back to the show.

2
00:00:05,000 --> 00:00:09,500
Um, today we we talk about habits, damn it is big.
"""
DIALOGUE = """HOST: Welcome back to the show everyone, great to have you here today.
GUEST: Thanks for having me, I think habits are, you know, the core of everything we do.
HOST: Let's start with the basics then.
"""
TIMESTAMPED = """[00:00] Welcome to the episode.
[00:12] HOST: Today is about focus and attention in a noisy world.
[01:05] It takes about 23 minutes to refocus after an interruption according to a 2008 study.
"""


def test_detects_formats_and_builds_segments():
    srt = text_ingest.build_segments(SRT)
    assert srt.format == "srt" and len(srt.segments) == 2
    assert srt.segments[1].start_ms == 5000 and srt.segments[1].end_ms == 9500
    dialogue = text_ingest.build_segments(DIALOGUE)
    assert dialogue.format == "dialogue" and dialogue.speakers == ["HOST", "GUEST"]
    assert dialogue.segments[0].text.startswith("HOST: ")
    stamped = text_ingest.build_segments(TIMESTAMPED)
    assert stamped.format == "timestamped" and stamped.segments[2].start_ms == 65_000 and stamped.segments[1].text.startswith("HOST: ")
    prose = text_ingest.build_segments("This is a plain article. " * 60, words_per_minute=150)
    assert prose.format == "prose" and len(prose.segments) >= 6
    assert abs(prose.estimated_duration_ms - 300 * 400) < 60_000  # 300 words at 150 wpm ≈ 2 min
    assert text_ingest.strip_speaker_labels(dialogue.segments).startswith("Welcome back")


def test_text_episode_from_paste_and_upload_and_meta():
    created = client.post("/v1/jobs/text", json={"text": SRT, "name": "pasted.srt"})
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["source_kind"] == "text" and job["stage"] == "waiting_for_approval" and job["voice_mode"] == "synthetic"
    kinds = {p["kind"] for p in job["proposals"]}
    assert {"filler", "repeat", "profanity"} <= kinds and "silence" not in kinds
    assert client.get(f"/v1/jobs/{job['id']}/audio/original").status_code == 404

    uploaded = client.post("/v1/jobs/text/upload", files={"file": ("notes.md", DIALOGUE.encode(), "text/markdown")})
    assert uploaded.status_code == 201 and uploaded.json()["media"]["codec"] == "text/dialogue"
    bad = client.post("/v1/jobs/text/upload", files={"file": ("clip.wav", b"RIFF....", "audio/wav")})
    assert bad.status_code == 422

    meta = client.patch(f"/v1/jobs/{job['id']}/meta", json={"display_name": "  My   Show  ", "tags": ["intro", " habits "], "notes": "first"})
    assert meta.status_code == 200 and meta.json()["display_name"] == "My Show" and meta.json()["tags"] == ["intro", "habits"]
    listing = client.get("/v1/jobs", params={"q": "habits"}).json()
    assert [item["display_name"] for item in listing] == ["My Show"]
    assert listing[0]["word_count"] > 0 and listing[0]["proposal_count"] >= 3

    archived = client.post("/v1/jobs/bulk", json={"ids": [job["id"]], "action": "archive"}).json()
    assert all(item["id"] != job["id"] or item["archived"] for item in archived)
    assert all(item["id"] != job["id"] for item in client.get("/v1/jobs").json())
    assert any(item["id"] == job["id"] for item in client.get("/v1/jobs", params={"include_archived": "true"}).json())

    other = uploaded.json()["id"]
    reordered = client.post("/v1/jobs/reorder", json={"ids": [other, job["id"]]}).json()
    assert [item["id"] for item in reordered][:2] == [other, job["id"]]
    deleted = client.post("/v1/jobs/bulk", json={"ids": [other], "action": "delete"})
    assert deleted.status_code == 200 and client.get(f"/v1/jobs/{other}").status_code == 404


def test_text_episode_render_requires_speech_provider():
    job = client.post("/v1/jobs/text", json={"text": DIALOGUE, "name": "dialogue.txt"}).json()
    approved = client.post(f"/v1/jobs/{job['id']}/approval", json={"decisions": [], "voice_mode": "synthetic", "title": "Dialogue"})
    assert approved.status_code == 200
    deadline = time.time() + 60
    while time.time() < deadline:
        current = client.get(f"/v1/jobs/{job['id']}").json()
        if current["stage"] in {"failed", "complete"}:
            break
        time.sleep(0.2)
    assert current["stage"] == "failed" and "speech provider" in current["error"].lower()


def test_stats_endpoint_reports_counts_and_timelines():
    job = client.post("/v1/jobs/text", json={"text": TIMESTAMPED, "name": "stamped.txt"}).json()
    stats = client.get(f"/v1/jobs/{job['id']}/stats").json()
    overview = stats["overview"]
    assert overview["words_original"] > 20 and overview["segments"] >= 3
    assert overview["words_per_minute"] > 0 and overview["unique_words"] <= overview["words_original"]
    assert set(stats["edits_by_kind"]) == {"profanity", "filler", "repeat", "silence", "noise"}
    assert len(stats["timeline"]["labels"]) == len(stats["timeline"]["words"]) >= 1
    assert sum(stats["timeline"]["words"]) == overview["words_original"]
    assert stats["top_words"] and all("count" in item for item in stats["top_words"])
    assert isinstance(stats["segment_length_histogram"], list) and sum(b["count"] for b in stats["segment_length_histogram"]) == overview["segments"]
