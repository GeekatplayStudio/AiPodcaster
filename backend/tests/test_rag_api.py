import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.transcription import FakeTranscriptionProvider

client = TestClient(app)

FACTS = (
    "# Habits research notes\n\n"
    "Building better habits takes on average 66 days according to a 2009 study by Phillippa Lally at University College London.\n\n"
    "Habit stacking, described by James Clear in Atomic Habits (2018), pairs a new habit with an existing routine.\n\n"
    "The book Atomic Habits has sold more than 15 million copies worldwide as of 2023.\n"
)


def wait_documents_ready(library_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        library = client.get(f"/v1/libraries/{library_id}").json()
        if library["documents"] and all(d["status"] in {"ready", "failed"} for d in library["documents"]):
            return library
        time.sleep(0.2)
    raise AssertionError("documents did not finish indexing")


def wait_verification(job_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["verification"]["status"] in {"complete", "failed"}:
            return job
        time.sleep(0.3)
    raise AssertionError("verification did not finish")


def make_library(name: str = "Research") -> dict:
    response = client.post("/v1/libraries", json={"name": name, "description": "notes"})
    assert response.status_code == 201, response.text
    return response.json()


def test_library_crud_upload_index_and_search():
    library = make_library()
    assert client.get("/v1/libraries").json()[0]["name"] == "Research"
    bad = client.post(f"/v1/libraries/{library['id']}/documents", files=[("files", ("virus.exe", b"MZ", "application/octet-stream"))])
    assert bad.status_code == 422
    uploaded = client.post(
        f"/v1/libraries/{library['id']}/documents",
        files=[("files", ("facts.md", FACTS.encode(), "text/markdown")), ("files", ("empty-ish.txt", b"Short note about habits that is long enough to index properly.", "text/plain"))],
    )
    assert uploaded.status_code == 201 and len(uploaded.json()) == 2
    ready = wait_documents_ready(library["id"])
    statuses = {d["name"]: d for d in ready["documents"]}
    assert statuses["facts.md"]["status"] == "ready" and statuses["facts.md"]["chunk_count"] >= 1
    summary = client.get("/v1/libraries").json()[0]
    assert summary["ready_count"] == 2 and summary["chunk_count"] >= 2

    hits = client.get(f"/v1/libraries/{library['id']}/search", params={"q": "how many days to form a habit"}).json()
    assert hits and hits[0]["document_name"] == "facts.md" and "66 days" in hits[0]["text"]

    doc_id = statuses["empty-ish.txt"]["id"]
    assert client.delete(f"/v1/libraries/{library['id']}/documents/{doc_id}").status_code == 204
    assert len(client.get(f"/v1/libraries/{library['id']}").json()["documents"]) == 1
    assert client.delete(f"/v1/libraries/{library['id']}").status_code == 204
    assert client.get(f"/v1/libraries/{library['id']}").status_code == 404


def test_projects_link_libraries_and_other_projects():
    lib_a, lib_b = make_library("A"), make_library("B")
    base = client.post("/v1/projects", json={"name": "Base show", "library_ids": [lib_a["id"]]})
    assert base.status_code == 201
    child = client.post("/v1/projects", json={"name": "Spin-off", "library_ids": [lib_b["id"]], "linked_project_ids": [base.json()["id"]]})
    assert child.status_code == 201
    effective = client.get(f"/v1/projects/{child.json()['id']}/libraries").json()
    assert set(effective) == {lib_a["id"], lib_b["id"]}
    self_link = client.put(f"/v1/projects/{child.json()['id']}", json={"name": "Spin-off", "linked_project_ids": [child.json()["id"]]})
    assert self_link.status_code == 422
    missing = client.post("/v1/projects", json={"name": "Broken", "library_ids": ["00000000-0000-4000-8000-000000000000"]})
    assert missing.status_code == 404
    assert client.delete(f"/v1/projects/{child.json()['id']}").status_code == 204


def test_fact_check_flags_contradiction_from_project_library(sample_wav, monkeypatch):
    # Make the fake transcript assert a figure that disagrees with the library.
    monkeypatch.setattr(FakeTranscriptionProvider, "script", "Welcome back to the show. Building better habits takes on average 21 days according to a 2009 study by Phillippa Lally at University College London. Um, let's get started.")
    library = make_library("Habits")
    client.post(f"/v1/libraries/{library['id']}/documents", files=[("files", ("facts.md", FACTS.encode(), "text/markdown"))])
    wait_documents_ready(library["id"])
    project = client.post("/v1/projects", json={"name": "Habits podcast", "library_ids": [library["id"]]}).json()

    with sample_wav.open("rb") as handle:
        created = client.post("/v1/jobs", files={"file": ("episode.wav", handle, "audio/wav")}, data={"project_id": project["id"]})
    assert created.status_code == 201 and created.json()["project_id"] == project["id"]
    job_id = created.json()["id"]
    deadline = time.time() + 120
    while client.get(f"/v1/jobs/{job_id}").json()["stage"] not in {"waiting_for_approval", "failed"} and time.time() < deadline:
        time.sleep(0.2)

    assert client.post(f"/v1/jobs/{job_id}/verify", json={"use_libraries": False, "use_online": False}).status_code == 422
    accepted = client.post(f"/v1/jobs/{job_id}/verify", json={"use_libraries": True, "use_online": False})
    assert accepted.status_code == 202
    job = wait_verification(job_id)
    report = job["verification"]
    assert report["status"] == "complete", report.get("error")
    assert report["used_libraries"] == ["Habits"] and report["judge"].startswith("heuristic")
    assert report["claims_checked"] >= 1
    flagged = [c for c in report["checks"] if c["flagged"]]
    assert flagged, report["checks"]
    assert "21" in flagged[0]["claim"] and flagged[0]["verdict"] == "contradicted"
    assert flagged[0]["evidence"][0]["source_kind"] == "library" and "66 days" in flagged[0]["evidence"][0]["excerpt"]

    dismissed = client.put(f"/v1/jobs/{job_id}/verify/decisions", json=[{"id": flagged[0]["id"], "dismissed": True}])
    assert dismissed.status_code == 200 and dismissed.json()["verification"]["flagged"] == len(flagged) - 1

    # Approve and render: the publish kit must now include the fact check report.
    approved = client.post(f"/v1/jobs/{job_id}/approval", json={"decisions": [], "voice_mode": "original", "title": "Habits"})
    assert approved.status_code == 200
    deadline = time.time() + 120
    while client.get(f"/v1/jobs/{job_id}").json()["stage"] not in {"complete", "failed"} and time.time() < deadline:
        time.sleep(0.3)
    done = client.get(f"/v1/jobs/{job_id}").json()
    assert done["stage"] == "complete", done.get("error")
    assert "habits-fact-check.md" in {o["name"] for o in done["outputs"]}
    text = client.get(f"/v1/jobs/{job_id}/outputs/habits-fact-check.md").text
    assert "Fact check report" in text and "21 days" in text
