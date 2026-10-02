"""Publish-kit generation: descriptions, hashtags, social posts (LLM or heuristic)
and episode thumbnails (OpenAI images or an offline Pillow cover)."""
from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from ..config import AppSettings
from ..providers import llm
from ..schemas import ProcessingJob, PublishKit

KIT_PROMPT = (
    "You are a podcast marketer. Using the transcript summary and chapters, write distribution copy. Return JSON with keys: "
    "title (<=80 chars), subtitle (<=120), short_description (<=300 chars, plain), long_description (3-5 paragraphs, plain text, ends with chapter list), "
    "hashtags (8-15 strings without #), keywords (8-12), social_posts (object with keys x, linkedin, instagram, threads; each a ready-to-post text), "
    "youtube_description (description + timestamps in MM:SS Title format + hashtags), thumbnail_prompt (visual description for an episode cover, no text in image), category.\n\n"
)
THUMB_SIZES = {"square": (1400, 1400), "youtube": (1280, 720)}


def heuristic_kit(job: ProcessingJob) -> PublishKit:
    notes = job.show_notes
    title = (job.publish_kit.title or notes.title or job.display_name or Path(job.asset_name).stem).strip()
    keywords = notes.keywords[:12]
    hashtags = [re.sub(r"[^A-Za-z0-9]", "", k.title()) for k in keywords if len(k) > 2][:12] + ["podcast"]
    chapters = "\n".join(f"{_mmss(c['start_ms'])} {c['title']}" for c in notes.chapters)
    summary = notes.summary or " ".join(s.text for s in job.segments[:3])
    short = summary[:297].rsplit(" ", 1)[0] + ("…" if len(summary) > 297 else "")
    long_description = f"{summary}\n\nIn this episode:\n{chapters}".strip()
    tags = " ".join(f"#{h}" for h in hashtags[:6])
    return PublishKit(
        title=title[:200],
        subtitle=(notes.chapters[0]["title"] if notes.chapters else "")[:300],
        short_description=short,
        long_description=long_description[:8000],
        hashtags=hashtags,
        keywords=keywords,
        social_posts={
            "x": f"New episode: {title}. {short[:150]} {tags}"[:280],
            "linkedin": f"New episode out now: {title}\n\n{short}\n\nListen now. {tags}",
            "instagram": f"{title} 🎙️\n\n{short}\n\n{' '.join('#' + h for h in hashtags)}",
            "threads": f"{title} — {short[:200]} {tags}",
        },
        youtube_description=f"{summary}\n\nChapters:\n{chapters}\n\n{tags}",
        thumbnail_prompt=f"Podcast episode cover illustration about {', '.join(keywords[:4]) or title}, bold modern flat design, high contrast, no text",
        category="",
        language=job.language or "",
        generated_by="heuristic",
        updated_at=datetime.now(UTC),
    )


def generate_kit(settings: AppSettings, job: ProcessingJob) -> PublishKit:
    fallback = heuristic_kit(job)
    if not llm.is_configured(settings):
        return fallback
    excerpt = " ".join(s.text for s in job.segments)[:12_000]
    keywords = ", ".join(job.show_notes.keywords)
    duration = _mmss(job.quality.final_duration_ms or job.media.duration_ms)
    body = (
        f"Title: {job.show_notes.title}\nSummary: {job.show_notes.summary}\nKeywords: {keywords}\n"
        f"Chapters: {json.dumps(job.show_notes.chapters)}\nDuration: {duration}\n\nTranscript excerpt:\n{excerpt}"
    )
    try:
        raw = llm.complete(settings, KIT_PROMPT + body, json_mode=True)
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else {}
    except Exception:  # noqa: BLE001 - never block publishing on the model
        return fallback
    if not isinstance(data, dict) or not data.get("title"):
        return fallback

    def text(key: str, limit: int, default: str) -> str:
        value = data.get(key)
        return str(value)[:limit] if isinstance(value, str) and value.strip() else default

    def words(key: str, default: list[str]) -> list[str]:
        value = data.get(key)
        return [str(v).lstrip("#")[:40] for v in value if str(v).strip()][:20] if isinstance(value, list) else default

    posts = data.get("social_posts") if isinstance(data.get("social_posts"), dict) else {}
    return PublishKit(
        title=text("title", 200, fallback.title),
        subtitle=text("subtitle", 300, fallback.subtitle),
        short_description=text("short_description", 600, fallback.short_description),
        long_description=text("long_description", 8000, fallback.long_description),
        hashtags=words("hashtags", fallback.hashtags),
        keywords=words("keywords", fallback.keywords),
        social_posts={k: str(v)[:3000] for k, v in posts.items()} or fallback.social_posts,
        youtube_description=text("youtube_description", 5000, fallback.youtube_description),
        thumbnail_prompt=text("thumbnail_prompt", 1500, fallback.thumbnail_prompt),
        category=text("category", 100, ""),
        language=job.language or "",
        generated_by=f"{settings.language_model.provider}:{llm.model_for(settings)}",
        updated_at=datetime.now(UTC),
    )


def generate_thumbnail(settings: AppSettings, job: ProcessingJob, prompt: str, target: Path, size: str = "square") -> str:
    """Return the generator name. Uses OpenAI images when configured, else a Pillow cover."""
    width, height = THUMB_SIZES.get(size, THUMB_SIZES["square"])
    if settings.images.provider == "openai" and settings.keys.openai_api_key:
        try:
            _openai_image(settings, prompt, target, width, height)
            return f"openai:{settings.images.model or 'gpt-image-1'}"
        except Exception as error:  # noqa: BLE001 - fall back to local cover
            _pillow_cover(job, target, width, height)
            return f"local (OpenAI failed: {str(error)[:80]})"
    _pillow_cover(job, target, width, height)
    return "local"


def _openai_image(settings: AppSettings, prompt: str, target: Path, width: int, height: int) -> None:
    import httpx

    model = settings.images.model or "gpt-image-1"
    size = "1024x1024" if width == height else "1536x1024"
    response = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {settings.keys.openai_api_key}"},
        json={"model": model, "prompt": prompt[:1500], "size": size, "n": 1},
        timeout=300,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"images API {response.status_code}: {response.text[:200]}")
    item = response.json()["data"][0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    else:
        raw = httpx.get(item["url"], timeout=120).content
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(raw)).convert("RGB").resize((width, height))
    image.save(target, "PNG")


def _pillow_cover(job: ProcessingJob, target: Path, width: int, height: int) -> None:
    from PIL import Image, ImageDraw

    title = (job.publish_kit.title or job.show_notes.title or job.display_name or job.asset_name)[:90]
    seed = sum(ord(c) for c in title) % 360
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        hue = (seed + 40 * t) % 360
        draw.line([(0, y), (width, y)], fill=_hsl(hue, 0.55, 0.22 + 0.18 * t))
    accent = _hsl((seed + 180) % 360, 0.7, 0.6)
    draw.rounded_rectangle([int(width * 0.06), int(height * 0.08), int(width * 0.06) + 14, int(height * 0.92)], radius=7, fill=accent)
    font_big = _font(int(min(width, height) * 0.075))
    font_small = _font(int(min(width, height) * 0.035))
    margin = int(width * 0.11)
    lines = _wrap(draw, title, font_big, width - 2 * margin)
    line_h = int(font_big.size * 1.2)
    top = int(height * 0.5) - line_h * len(lines) // 2
    for index, line in enumerate(lines[:5]):
        draw.text((margin, top + index * line_h), line, font=font_big, fill="white")
    draw.text((margin, int(height * 0.08)), "PODCAST EPISODE", font=font_small, fill=accent)
    duration = job.quality.final_duration_ms or job.media.duration_ms
    draw.text((margin, int(height * 0.88)), f"{_mmss(duration)} · {len(job.show_notes.chapters)} chapters", font=font_small, fill=(230, 230, 230))
    image.save(target, "PNG")


def _font(size: int):
    from PIL import ImageFont

    for candidate in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, max_width: int) -> list[str]:  # noqa: ANN001
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _hsl(h: float, s: float, light: float) -> tuple[int, int, int]:
    import colorsys

    r, g, b = colorsys.hls_to_rgb(h / 360, light, s)
    return int(r * 255), int(g * 255), int(b * 255)


def _mmss(ms: int) -> str:
    minutes, seconds = divmod(int(ms or 0) // 1000, 60)
    return f"{minutes:02d}:{seconds:02d}"
