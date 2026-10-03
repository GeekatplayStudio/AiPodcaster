"""Optional language-model enrichment (title, summary, chapters, keywords).

Works fully offline with a heuristic fallback so the pipeline never depends on
a paid API. When OpenAI or Anthropic is configured the result is upgraded.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from ..config import AppSettings
from ..providers import llm as backend
from ..schemas import ShowNotes, TranscriptSegment
from . import languages

STOPWORDS = set(
    "the a an and or but so to of in on for with at by from is are was were be been being this that these those it its i you we they he she them "
    "our your their my me us him her as if then than there here what which who whom how when where why not no yes do does did have has had "
    "will would can could should may might just very really also about into over out up down like um uh okay ok well yeah right get got go going".split()
)
PROMPT = (
    "You are a podcast producer. Given this transcript, return JSON with keys: "
    "title (max 80 chars), summary (2-3 sentences for show notes), keywords (5-10 strings), "
    "chapters (3-8 objects with start_ms and title, where start_ms is copied from the nearest segment start). "
    "Return only JSON.\n\nSegments (id, start_ms, text):\n"
)


def _heuristic(segments: list[TranscriptSegment], fallback_title: str) -> ShowNotes:
    stop = STOPWORDS | languages.all_stopwords()
    words = [w for s in segments for w in re.findall(r"[^\W\d_]{3,}", s.text.lower()) if w not in stop]
    keywords = [word for word, _ in Counter(words).most_common(8)]
    total = max(len(segments), 1)
    chapter_count = min(6, max(1, total // 12))
    step = max(1, total // chapter_count)
    chapters = []
    for index in range(0, total, step):
        if len(chapters) >= chapter_count:
            break
        segment = segments[index]
        title = " ".join(segment.text.split()[:7]).rstrip(",.;:") or f"Part {len(chapters) + 1}"
        chapters.append({"start_ms": segment.start_ms, "title": title})
    if chapters:
        chapters[0]["start_ms"] = 0
        chapters[0]["title"] = "Introduction" if len(chapters) > 1 else chapters[0]["title"]
    summary = " ".join(segment.text for segment in segments[:3]).strip()
    if len(summary) > 400:
        summary = summary[:397].rsplit(" ", 1)[0] + "..."
    return ShowNotes(title=fallback_title, summary=summary, chapters=chapters, keywords=keywords, generated_by="heuristic")


def _segments_text(segments: list[TranscriptSegment]) -> str:
    lines = [f"{s.id}\t{s.start_ms}\t{s.text}" for s in segments]
    text = "\n".join(lines)
    return text[:60_000]


def _parse(raw: str, segments: list[TranscriptSegment], fallback: ShowNotes, provider: str) -> ShowNotes:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback
    starts = {s.start_ms for s in segments}
    chapters = []
    for chapter in data.get("chapters", []) if isinstance(data.get("chapters"), list) else []:
        try:
            start = int(chapter.get("start_ms", 0))
            title = str(chapter.get("title", "")).strip()[:120]
        except (AttributeError, TypeError, ValueError):
            continue
        if title:
            nearest = min(starts, key=lambda s: abs(s - start)) if starts else start
            chapters.append({"start_ms": max(0, nearest), "title": title})
    chapters.sort(key=lambda c: c["start_ms"])
    keywords = [str(k)[:40] for k in data.get("keywords", [])][:10] if isinstance(data.get("keywords"), list) else fallback.keywords
    return ShowNotes(
        title=str(data.get("title") or fallback.title)[:120],
        summary=str(data.get("summary") or fallback.summary)[:2000],
        chapters=chapters or fallback.chapters,
        keywords=keywords,
        generated_by=provider,
    )


def generate_show_notes(settings: AppSettings, segments: list[TranscriptSegment], fallback_title: str, language: str | None = None) -> ShowNotes:
    fallback = _heuristic(segments, fallback_title)
    provider = settings.language_model.provider
    if provider == "none" or not segments:
        return fallback
    prompt = PROMPT + language_instruction(language) + "\n\n" + _segments_text(segments)
    if not backend.is_configured(settings):
        return fallback
    try:
        return _parse(backend.complete(settings, prompt, json_mode=True), segments, fallback, f"{provider}:{backend.model_for(settings)}")
    except Exception:  # noqa: BLE001 - enrichment must never fail the job
        return fallback


def language_instruction(language: str | None) -> str:
    """Tell the model to answer in the transcript's language."""
    if not language:
        return "Write every text value in the same language as the transcript."
    return f"Write every text value in {languages.language_name(language)} (the transcript language)."
