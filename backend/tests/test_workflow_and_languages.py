import shutil
import time
from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import JobStage, ProcessingJob, Word
from app.services import languages, naming, pipeline, workflow
from app.services.analysis import find_fillers, find_profanity
from app.storage import job_store

client = TestClient(app)


def wait_stage(job_id, stages, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["stage"] in stages:
            return job
        time.sleep(0.2)
    raise AssertionError(f"timed out: {job['stage']} {job.get('error')}")


def words(*tokens):
    return [Word(text=t, start_ms=i * 400, end_ms=i * 400 + 300) for i, t in enumerate(tokens)]


def test_workflow_resumes_at_interrupted_node_without_redoing_earlier_work(sample_wav):
    job = job_store.create(ProcessingJob(asset_name="resume.wav"))
    shutil.copy(sample_wav, pipeline.source_path(job_store, job.id))
    job.pipeline_run = 1
    job_store.save(job)
    config = workflow._config(job.id, 1)
    # Simulate a server stop right before transcription.
    workflow.graph().invoke({"job_id": str(job.id), "phase": "analysis"}, config, interrupt_before=["transcribe"])
    assert workflow.graph().get_state(config).next == ("transcribe",)
    canonical = pipeline.canonical_wav(job_store, job.id)
    ingest_mtime = canonical.stat().st_mtime_ns
    stuck = job_store.get(job.id)
    stuck.stage = JobStage.TRANSCRIBE
    job_store.save(stuck)

    resumed = workflow.resume_incomplete()
    assert job.id in resumed
    done = wait_stage(str(job.id), {"waiting_for_approval", "failed"})
    assert done["stage"] == "waiting_for_approval", done.get("error")
    assert canonical.stat().st_mtime_ns == ingest_mtime  # ingest was not repeated
    assert workflow.paused_before_render(job.id, 1)


def test_approval_right_after_review_is_not_lost(sample_wav):
    with sample_wav.open("rb") as handle:
        job = client.post("/v1/jobs", files={"file": ("race.wav", handle, "audio/wav")}).json()
    job = wait_stage(job["id"], {"waiting_for_approval"})
    # Approve immediately; the worker may still be releasing the job.
    assert client.post(f"/v1/jobs/{job['id']}/approval", json={"decisions": [], "voice_mode": "original", "title": "Race"}).status_code == 200
    assert wait_stage(job["id"], {"complete", "failed"})["stage"] == "complete"


def test_draft_autosave_persists_decisions_title_and_voice(sample_wav):
    with sample_wav.open("rb") as handle:
        job = client.post("/v1/jobs", files={"file": ("draft.wav", handle, "audio/wav")}).json()
    job = wait_stage(job["id"], {"waiting_for_approval"})
    target = job["proposals"][0]
    saved = client.put(f"/v1/jobs/{job['id']}/draft", json={"decisions": [{"id": target["id"], "accepted": not target["accepted"]}], "title": "Draft title", "voice_mode": "original"})
    assert saved.status_code == 200
    fresh = client.get(f"/v1/jobs/{job['id']}").json()
    assert fresh["proposals"][0]["accepted"] is (not target["accepted"])
    assert fresh["show_notes"]["title"] == "Draft title" and fresh["stage"] == "waiting_for_approval"
    # "draft.wav" is not generic, so its name is kept; a generated date name would be replaced.
    assert fresh["display_name"] == "" and fresh["auto_named"] is False
    bad = client.put(f"/v1/jobs/{job['id']}/draft", json={"decisions": [{"id": "00000000-0000-4000-8000-000000000000", "accepted": True}]})
    assert bad.status_code == 422


def test_generic_names_become_dates():
    moment = datetime(2026, 10, 2, 17, 45)
    assert naming.display_name_for("audio.wav", moment) == "Episode 2026-10-02 17:45"
    assert naming.display_name_for("20261002_174512.mp4", moment) == "Episode 2026-10-02 17:45"
    assert naming.display_name_for("New Recording 3.m4a", moment) == "Episode 2026-10-02 17:45"
    assert naming.display_name_for("", moment) == "Episode 2026-10-02 17:45"
    assert naming.display_name_for("deep-focus-ep14.wav", moment) == ""
    text = client.post("/v1/jobs/text", json={"text": "Welcome back to the show, today we are talking about habits and focus."}).json()
    assert text["display_name"].startswith("Episode 20") and text["asset_name"].startswith("episode-20") and text["auto_named"]
    titled = client.put(f"/v1/jobs/{text['id']}/draft", json={"decisions": [], "title": "  Habits   and focus "}).json()
    assert titled["display_name"] == "Habits and focus" and titled["auto_named"] is False
    again = client.put(f"/v1/jobs/{text['id']}/draft", json={"decisions": [], "title": "Another title"}).json()
    assert again["display_name"] == "Habits and focus"  # only the generated name is replaced


def test_multilingual_fillers_elongations_and_profanity():
    ru = find_fillers(words("Аааа,", "я", "думаю,", "ммм,", "что", "э-э-э", "как", "бы", "нууу", "а", "хорошо"), [], "ru")
    assert [(p.text, p.accepted) for p in ru] == [("Аааа,", True), ("ммм,", True), ("э-э-э", True), ("как бы", False), ("нууу", True)]
    en = find_fillers(words("Hmmm", "so", "the", "eeee", "answer", "is", "a", "good", "Ummm"), [], "en")
    assert {p.text for p in en} == {"Hmmm", "so", "eeee", "Ummm"}
    assert not any(p.text in {"a", "good"} for p in en)
    es = find_fillers(words("Eeeh,", "o", "sea,", "esteee", "es", "este", "libro"), [], "es")
    assert [(p.text, p.accepted) for p in es] == [("Eeeh,", True), ("o sea,", False), ("esteee", True), ("este", False)]
    clean_ru = "употреблять рубля страхуйте хлебанул небо обед мудрый сукно".split()
    assert find_profanity(words(*clean_ru), [], "ru") == []
    assert [p.text for p in find_profanity(words("нахуй", "заебись", "пиздец", "блядь"), [], "ru")] == ["нахуй", "заебись", "пиздец", "блядь"]
    assert [p.text for p in find_profanity(words("joder", "libro", "mierda"), [], "es")] == ["joder", "mierda"]
    assert languages.verbatim_prompt("ru").startswith("Ээ")


def test_text_episode_detects_language_and_reanalyses_with_override():
    text = "Ээ, привет всем. Ммм, сегодня мы, как бы, поговорим о том, как это работает. Нууу, начнём с самого простого и понятного примера."
    job = client.post("/v1/jobs/text", json={"text": text, "name": "Выпуск 1"}).json()
    assert job["language"] == "ru"
    assert {"Ээ,", "Ммм,", "Нууу,"} <= {p["text"] for p in job["proposals"]}
    patched = client.patch(f"/v1/jobs/{job['id']}/meta", json={"language": "uk"}).json()
    assert patched["language_override"] == "uk"
    again = client.post(f"/v1/jobs/{job['id']}/reanalyze").json()
    assert again["language"] == "uk" and again["stage"] == "waiting_for_approval"
    assert client.patch(f"/v1/jobs/{job['id']}/meta", json={"language": "auto"}).json()["language_override"] is None
    assert client.patch(f"/v1/jobs/{job['id']}/meta", json={"language": "not a code"}).status_code == 422


def test_info_endpoint_reports_languages_and_estimates():
    info = client.get("/v1/info").json()
    assert info["languages"]["ru"] == "Russian" and info["public_url"].startswith("http")
    assert info["estimates"]["analysis_rtf"] >= 0 and info["estimates"]["long_recording_seconds"] == 1800
    assert UUID  # keep import used
