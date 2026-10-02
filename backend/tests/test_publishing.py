import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.publishing import connectors

client = TestClient(app)
TEXT = "HOST: Welcome to the focus episode. It takes about 23 minutes to refocus after an interruption. GUEST: That matches the 2008 study by Gloria Mark. HOST: Let's talk about deep work and attention habits for remote teams."


def make_job() -> dict:
    return client.post("/v1/jobs/text", json={"text": TEXT, "name": "focus.txt"}).json()


def test_kit_generation_thumbnail_and_package():
    job = make_job()
    generated = client.post(f"/v1/jobs/{job['id']}/kit/generate").json()
    kit = generated["publish_kit"]
    assert kit["title"] and kit["short_description"] and kit["hashtags"] and kit["generated_by"] == "heuristic"
    assert set(kit["social_posts"]) >= {"x", "linkedin", "instagram"} and len(kit["social_posts"]["x"]) <= 280

    kit["title"] = "Focus, Interrupted"
    kit["hashtags"] = ["focus", "deepwork"]
    kit["episode_number"] = 7
    updated = client.put(f"/v1/jobs/{job['id']}/kit", json=kit).json()["publish_kit"]
    assert updated["title"] == "Focus, Interrupted" and updated["episode_number"] == 7

    thumb = client.post(f"/v1/jobs/{job['id']}/kit/thumbnail", json={"size": "youtube"})
    assert thumb.status_code == 200, thumb.text
    assert thumb.json()["publish_kit"]["thumbnail_file"] == "thumbnail-youtube.png"
    image = client.get(f"/v1/jobs/{job['id']}/kit/thumbnail")
    assert image.status_code == 200 and image.content[:4] == b"\x89PNG"
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(image.content)).size == (1280, 720)

    bad = client.post(f"/v1/jobs/{job['id']}/kit/thumbnail/upload", files={"file": ("x.gif", b"GIF89a....", "image/gif")})
    assert bad.status_code == 422
    good = client.post(f"/v1/jobs/{job['id']}/kit/thumbnail/upload", files={"file": ("c.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")})
    assert good.status_code == 200 and good.json()["publish_kit"]["thumbnail_file"] == "thumbnail-custom.png"

    package = client.get(f"/v1/jobs/{job['id']}/publish/package")
    assert package.status_code == 200 and package.headers["content-type"] == "application/zip"
    import zipfile
    from io import BytesIO as B

    names = set(zipfile.ZipFile(B(package.content)).namelist())
    assert {"manifest.json", "description.txt", "hashtags.txt", "social-x.txt", "thumbnail-custom.png"} <= names


def test_targets_crud_masks_secrets_and_validates():
    catalog = client.get("/v1/publish/catalog").json()
    assert {k["id"] for k in catalog} >= {"generic_webhook", "wordpress", "buzzsprout", "transistor", "spotify_for_creators", "youtube"}
    missing = client.post("/v1/publish/targets", json={"name": "Site", "kind": "generic_webhook", "config": {"url": "https://example.com/hook"}})
    assert missing.status_code == 422
    created = client.post("/v1/publish/targets", json={"name": "Site", "kind": "generic_webhook", "config": {"url": "https://example.com/hook", "secret": "s3cret"}})
    assert created.status_code == 201 and created.json()["config"]["secret"] == "••••••••"
    target_id = created.json()["id"]
    updated = client.put(f"/v1/publish/targets/{target_id}", json={"name": "Site 2", "kind": "generic_webhook", "config": {"url": "https://example.com/hook2", "secret": "••••••••"}}).json()
    assert updated["name"] == "Site 2" and updated["config"]["url"] == "https://example.com/hook2"
    from uuid import UUID

    from app.publishing.store import target_store

    assert target_store.get(UUID(target_id)).config["secret"] == "s3cret"  # mask did not overwrite
    bad_url = client.post("/v1/publish/targets", json={"name": "x", "kind": "wordpress", "config": {"site_url": "ftp://x", "username": "u", "app_password": "p"}})
    assert bad_url.status_code == 422
    assert client.delete(f"/v1/publish/targets/{target_id}").status_code == 204
    assert client.get("/v1/publish/targets").json() == []


def test_publish_webhook_and_manual_targets(monkeypatch):
    job = make_job()
    client.post(f"/v1/jobs/{job['id']}/kit/generate")
    hook = client.post("/v1/publish/targets", json={"name": "My site", "kind": "generic_webhook", "config": {"url": "https://example.com/hook", "secret": "s"}}).json()
    # API targets need a produced MP3.
    blocked = client.post(f"/v1/jobs/{job['id']}/publish", json={"target_id": hook["id"]})
    assert blocked.status_code == 409

    # Fake a produced episode by registering an MP3 output.
    from uuid import UUID

    from app.schemas import OutputFile
    from app.storage import job_store

    stored = job_store.get(UUID(job["id"]))
    (job_store.output_dir(stored.id) / "focus.mp3").write_bytes(b"ID3fake")
    stored.outputs.append(OutputFile(name="focus.mp3", label="Episode (MP3)", size_bytes=7, content_type="audio/mpeg"))
    job_store.save(stored)

    seen = {}

    def fake_post(url, headers=None, files=None, timeout=None, **kwargs):
        seen["url"], seen["headers"], seen["files"] = url, headers, files
        return httpx.Response(200, json={"message": "stored", "url": "https://example.com/episodes/7"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    published = client.post(f"/v1/jobs/{job['id']}/publish", json={"target_id": hook["id"]}).json()
    record = published["publish_history"][0]
    assert record["status"] == "success" and record["url"] == "https://example.com/episodes/7"
    assert seen["headers"]["X-AiPodcaster-Secret"] == "s" and "audio" in seen["files"] and "manifest" in seen["files"]
    manifest = json.loads(seen["files"]["manifest"][1])
    assert manifest["title"] and manifest["transcript"] and manifest["generator"] == "AiPodcaster"
    assert client.get("/v1/publish/targets").json()[0]["last_result"].startswith("success")

    def failing_post(*args, **kwargs):
        return httpx.Response(500, text="boom", request=httpx.Request("POST", "https://example.com/hook"))

    monkeypatch.setattr(httpx, "post", failing_post)
    failed = client.post(f"/v1/jobs/{job['id']}/publish", json={"target_id": hook["id"]}).json()["publish_history"][0]
    assert failed["status"] == "failed" and "500" in failed["message"]

    manual = client.post("/v1/publish/targets", json={"name": "Spotify", "kind": "spotify_for_creators", "config": {}}).json()
    result = client.post(f"/v1/jobs/{job['id']}/publish", json={"target_id": manual["id"]}).json()["publish_history"][0]
    assert result["status"] == "manual" and "Checklist" in result["message"]
    listing = client.get("/v1/jobs").json()
    assert next(item for item in listing if item["id"] == job["id"])["published"] == 1


def test_wordpress_connector_builds_post(monkeypatch):
    from app.publishing.schemas import PublishTarget
    from app.schemas import ProcessingJob, PublishKit

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("/media"):
                return httpx.Response(201, json={"id": 5, "source_url": "https://blog/x.mp3"}, request=httpx.Request("POST", url))
            return httpx.Response(201, json={"link": "https://blog/?p=1"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "Client", FakeClient)
    target = PublishTarget(name="Blog", kind="wordpress", config={"site_url": "https://blog", "username": "u", "app_password": "p", "status": "publish"})
    job = ProcessingJob(asset_name="a.wav", publish_kit=PublishKit(title="T", long_description="Body", hashtags=["a"]))
    package = connectors.Package(audio=None, thumbnail=None, manifest=connectors.build_manifest(job, "http://api"))
    status, message, url = connectors.publish(target, job, package)
    assert status == "success" and url == "https://blog/?p=1" and "publish" in message
    post_payload = calls[-1][1]["json"]
    assert post_payload["title"] == "T" and "#a" in post_payload["content"] and post_payload["status"] == "publish"
    with pytest.raises(connectors.PublishError):
        connectors.publish(PublishTarget(name="x", kind="rss", config={}).model_copy(update={"kind": "nope"}), job, package)
