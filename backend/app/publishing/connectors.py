"""Connectors push a finished episode to a hosting service or website.

Each connector receives the job, the local file paths and the publish kit, and
returns a (status, message, url). API connectors use httpx; manual kinds return
status "manual" together with the checklist the user has to complete.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from ..schemas import ProcessingJob
from .schemas import PublishTarget, kind_by_id


class PublishError(RuntimeError):
    pass


@dataclass
class Package:
    audio: Path | None
    thumbnail: Path | None
    manifest: dict


def build_manifest(job: ProcessingJob, api_url: str) -> dict:
    kit = job.publish_kit
    return {
        "episode_id": str(job.id),
        "title": kit.title or job.show_notes.title,
        "subtitle": kit.subtitle,
        "description": kit.long_description or job.show_notes.summary,
        "short_description": kit.short_description,
        "hashtags": kit.hashtags,
        "keywords": kit.keywords or job.show_notes.keywords,
        "chapters": job.show_notes.chapters,
        "duration_seconds": round(job.quality.final_duration_ms / 1000, 1),
        "language": kit.language or job.language,
        "explicit": kit.explicit,
        "episode_number": kit.episode_number,
        "season_number": kit.season_number,
        "category": kit.category,
        "transcript": [{"start_ms": s.start_ms, "text": s.text} for s in job.segments],
        "outputs": [{"name": o.name, "label": o.label, "url": f"{api_url}/v1/jobs/{job.id}/outputs/{o.name}"} for o in job.outputs],
        "generator": "AiPodcaster",
    }


def _html_description(job: ProcessingJob, audio_url: str | None) -> str:
    kit = job.publish_kit
    chapters = "".join(f"<li>{_mmss(c['start_ms'])} — {_esc(c['title'])}</li>" for c in job.show_notes.chapters)
    player = f'<!-- wp:audio --><figure class="wp-block-audio"><audio controls src="{audio_url}"></audio></figure><!-- /wp:audio -->' if audio_url else ""
    tags = " ".join(f"#{t.lstrip('#')}" for t in kit.hashtags)
    return f"{player}<p>{_esc(kit.long_description or job.show_notes.summary)}</p><h3>Chapters</h3><ul>{chapters}</ul><p>{_esc(tags)}</p>"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mmss(ms: int) -> str:
    minutes, seconds = divmod(int(ms) // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _check(response, service: str) -> dict:  # noqa: ANN001
    if response.status_code >= 400:
        raise PublishError(f"{service} returned {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError:
        return {}


def publish_generic_webhook(target: PublishTarget, job: ProcessingJob, package: Package) -> tuple[str, str, str | None]:
    import httpx

    headers = {"X-AiPodcaster-Secret": target.config.get("secret", ""), "X-AiPodcaster-Event": "episode.publish"}
    files = {"manifest": ("manifest.json", json.dumps(package.manifest).encode(), "application/json")}
    if package.audio and package.audio.exists():
        files["audio"] = (package.audio.name, package.audio.read_bytes(), "audio/mpeg")
    if package.thumbnail and package.thumbnail.exists():
        files["thumbnail"] = (package.thumbnail.name, package.thumbnail.read_bytes(), "image/png")
    data = _check(httpx.post(target.config["url"], headers=headers, files=files, timeout=600), "Webhook")
    return "success", str(data.get("message", "Delivered to website")), data.get("url")


def publish_wordpress(target: PublishTarget, job: ProcessingJob, package: Package) -> tuple[str, str, str | None]:
    import httpx

    base = target.config["site_url"].rstrip("/") + "/wp-json/wp/v2"
    token = base64.b64encode(f"{target.config['username']}:{target.config['app_password']}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    audio_url, media_id = None, None
    with httpx.Client(headers=headers, timeout=600) as client:
        if package.audio and package.audio.exists():
            response = client.post(f"{base}/media", headers={"Content-Disposition": f'attachment; filename="{package.audio.name}"', "Content-Type": "audio/mpeg"}, content=package.audio.read_bytes())
            audio_url = _check(response, "WordPress media").get("source_url")
        if package.thumbnail and package.thumbnail.exists():
            response = client.post(f"{base}/media", headers={"Content-Disposition": f'attachment; filename="{package.thumbnail.name}"', "Content-Type": "image/png"}, content=package.thumbnail.read_bytes())
            media_id = _check(response, "WordPress media").get("id")
        post = {"title": package.manifest["title"], "content": _html_description(job, audio_url), "status": target.config.get("status") or "draft", "excerpt": package.manifest["short_description"]}
        if media_id:
            post["featured_media"] = media_id
        created = _check(client.post(f"{base}/posts", json=post), "WordPress posts")
    return "success", f"Post created as {post['status']}", created.get("link")


def publish_buzzsprout(target: PublishTarget, job: ProcessingJob, package: Package) -> tuple[str, str, str | None]:
    import httpx

    url = f"https://www.buzzsprout.com/api/{target.config['podcast_id']}/episodes.json"
    headers = {"Authorization": f"Token token={target.config['api_token']}"}
    data = {"title": package.manifest["title"], "description": package.manifest["description"], "summary": package.manifest["short_description"], "explicit": str(package.manifest["explicit"]).lower(), "tags": ", ".join(package.manifest["keywords"])}
    if package.manifest.get("episode_number") is not None:
        data["episode_number"] = str(package.manifest["episode_number"])
    files = {}
    if package.audio and package.audio.exists():
        files["audio_file"] = (package.audio.name, package.audio.read_bytes(), "audio/mpeg")
    if package.thumbnail and package.thumbnail.exists():
        files["artwork_file"] = (package.thumbnail.name, package.thumbnail.read_bytes(), "image/png")
    created = _check(httpx.post(url, headers=headers, data=data, files=files or None, timeout=900), "Buzzsprout")
    return "success", "Episode created on Buzzsprout", created.get("audio_url") or created.get("private_url")


def publish_transistor(target: PublishTarget, job: ProcessingJob, package: Package) -> tuple[str, str, str | None]:
    import httpx

    headers = {"x-api-key": target.config["api_key"]}
    with httpx.Client(base_url="https://api.transistor.fm/v1", headers=headers, timeout=900) as client:
        audio_url = None
        if package.audio and package.audio.exists():
            auth = _check(client.get("/episodes/authorize_upload", params={"filename": package.audio.name}), "Transistor")["data"]["attributes"]
            put = httpx.put(auth["upload_url"], content=package.audio.read_bytes(), headers={"Content-Type": "audio/mpeg"}, timeout=900)
            if put.status_code >= 400:
                raise PublishError(f"Transistor upload failed ({put.status_code})")
            audio_url = auth["audio_url"]
        episode = {
            "show_id": target.config["show_id"],
            "title": package.manifest["title"],
            "summary": package.manifest["short_description"],
            "description": package.manifest["description"],
            "audio_url": audio_url,
            "explicit": package.manifest["explicit"],
            "keywords": ", ".join(package.manifest["keywords"]),
        }
        payload = {"episode": episode}
        created = _check(client.post("/episodes", json=payload), "Transistor")
    return "success", "Episode created on Transistor", created.get("data", {}).get("attributes", {}).get("share_url")


MANUAL_CHECKLISTS = {
    "spotify_for_creators": ["Open Spotify for Creators → New episode", "Upload the MP3 from the publish kit", "Paste the title and long description", "Add the cover image (min 1400×1400)", "Set explicit flag and season/episode numbers", "Publish or schedule"],
    "apple_podcasts": ["Episodes reach Apple through your RSS host", "Verify artwork is 3000×3000 PNG/JPG", "Use the Apple-safe title (no episode numbers in title)", "Check category and explicit flag in Podcasts Connect"],
    "youtube": ["Create a video from the MP3 plus thumbnail (or use a static-image video)", "Paste the YouTube description with chapters (timestamps enable YouTube chapters)", "Add the hashtags", "Upload the 1280×720 thumbnail"],
    "rss": ["Paste the RSS item snippet from the publish kit into your host's new-episode form", "Upload the MP3 and cover", "Keep the GUID stable if you republish"],
}

CONNECTORS = {"generic_webhook": publish_generic_webhook, "wordpress": publish_wordpress, "buzzsprout": publish_buzzsprout, "transistor": publish_transistor}


def publish(target: PublishTarget, job: ProcessingJob, package: Package) -> tuple[str, str, str | None]:
    kind = kind_by_id(target.kind)
    if kind is None:
        raise PublishError("Unknown target kind")
    if kind.mode == "manual":
        steps = MANUAL_CHECKLISTS.get(target.kind, [])
        return "manual", "Package prepared. Checklist: " + " → ".join(steps), kind.docs_url or None
    connector = CONNECTORS[target.kind]
    return connector(target, job, package)
