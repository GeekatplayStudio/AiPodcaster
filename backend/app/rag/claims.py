"""Pick checkable factual statements out of a transcript.

Heuristic extraction works offline; when a language model is configured it is
used to extract cleaner, self-contained claims instead.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..config import AppSettings
from ..providers import llm
from ..schemas import TranscriptSegment
from ..services.languages import all_stopwords

NUMBER = re.compile(r"\b\d[\d,.]*\s*(%|percent|million|billion|thousand|hundred|km|miles?|metres?|meters?|feet|years?|months?|weeks?|days?|hours?|minutes?|seconds?|kg|pounds?|tons?|dollars?|euros?|people|copies|times)?\b", re.I)
YEAR = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
ASSERTIVE = re.compile(r"\b(is|are|was|were|has|have|had|invented|founded|discovered|born|died|won|costs?|measures?|contains?|causes?|means|located|largest|smallest|first|only)\b", re.I)
OPINION = re.compile(
    r"\b(i think|i feel|i believe|in my opinion|maybe|probably|i guess|kind of|sort of|you know|let's|welcome|thanks?|"
    r"я думаю|мне кажется|по-моему|наверное|может быть|спасибо|добро пожаловать|creo que|me parece|quizás|gracias|bienvenidos|"
    r"ich glaube|ich denke|vielleicht|danke|willkommen|je pense|je crois|peut-être|merci|bienvenue|penso che|forse|grazie|acho que|talvez|obrigad[oa])\b",
    re.I,
)
STOP = set("the a an and or but so to of in on for with at by from is are was were be been this that these those it its as if then than there here what which who how when where why not no".split()) | set(all_stopwords())
PROMPT = (
    "Extract factual, verifiable claims from this podcast transcript. Ignore opinions, greetings, jokes and questions. "
    "Rewrite each claim as a short self-contained sentence (resolve pronouns). Return JSON: {\"claims\": [{\"segment_id\": int, \"claim\": str}]}. "
    "At most {limit} claims, most important first.\n\nSegments (id | text):\n"
)


@dataclass
class Claim:
    segment_id: int
    start_ms: int
    text: str
    score: float


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _proper_nouns(sentence: str) -> int:
    words = sentence.split()
    return sum(1 for word in words[1:] if word[:1].isupper() and word.strip(".,;:!?").isalpha())


def score_sentence(sentence: str) -> float:
    words = sentence.split()
    if len(words) < 5 or sentence.endswith("?"):
        return 0.0
    score = 0.0
    if NUMBER.search(sentence):
        score += 0.45
    if YEAR.search(sentence):
        score += 0.2
    score += min(_proper_nouns(sentence), 3) * 0.15
    if ASSERTIVE.search(sentence):
        score += 0.2
    if OPINION.search(sentence):
        score -= 0.4
    if len(words) > 45:
        score -= 0.15
    return max(0.0, min(1.0, score))


def heuristic_claims(segments: list[TranscriptSegment], limit: int) -> list[Claim]:
    candidates: list[Claim] = []
    for segment in segments:
        for sentence in split_sentences(segment.text):
            score = score_sentence(sentence)
            if score >= 0.35:
                candidates.append(Claim(segment.id, segment.start_ms, sentence, score))
    candidates.sort(key=lambda c: (-c.score, c.start_ms))
    chosen = candidates[:limit]
    chosen.sort(key=lambda c: c.start_ms)
    return chosen


def llm_claims(settings: AppSettings, segments: list[TranscriptSegment], limit: int, language: str | None = None) -> list[Claim] | None:
    provider = settings.language_model.provider
    if provider == "none" or not llm.is_configured(settings):
        return None
    body = "\n".join(f"{s.id} | {s.text}" for s in segments)[:80_000]
    prompt = PROMPT.replace("{limit}", str(limit)) + body + "\n\nKeep each claim in the transcript's language."
    try:
        raw = llm.complete(settings, prompt, json_mode=True)
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0)) if match else {}
    except Exception:  # noqa: BLE001 - fall back to heuristics
        return None
    by_id = {s.id: s for s in segments}
    claims: list[Claim] = []
    for item in data.get("claims", []) if isinstance(data.get("claims"), list) else []:
        try:
            segment = by_id[int(item["segment_id"])]
            text = str(item["claim"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if text:
            claims.append(Claim(segment.id, segment.start_ms, text[:1000], 0.8))
    claims.sort(key=lambda c: c.start_ms)
    return claims[:limit] or None


def extract_claims(settings: AppSettings, segments: list[TranscriptSegment], language: str | None = None) -> tuple[list[Claim], str]:
    limit = settings.fact_check.max_claims
    via_llm = llm_claims(settings, segments, limit, language)
    if via_llm:
        return via_llm, settings.language_model.provider
    return heuristic_claims(segments, limit), "heuristic"


def keywords(text: str, limit: int = 8) -> list[str]:
    words = [w.strip(".,;:!?'\"") for w in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}|\d[\d,.]*", text)]
    ranked = sorted({w for w in words if w.lower() not in STOP}, key=lambda w: (-(w[:1].isupper() or w[:1].isdigit()), -len(w)))
    return ranked[:limit]


def numbers_in(text: str) -> set[str]:
    return {re.sub(r"[,\s]", "", m.group(0)).rstrip(".").lower() for m in NUMBER.finditer(text)}


def figures_in(text: str) -> dict[str, set[str]]:
    """Numbers grouped by unit, e.g. {"days": {"21"}, "year": {"2009"}, "": {"3"}}."""
    groups: dict[str, set[str]] = {}
    for match in NUMBER.finditer(text):
        raw = match.group(0)
        value = re.sub(r"[^\d.]", "", raw).rstrip(".")
        unit = (match.group(1) or "").lower().rstrip("s") or ("year" if YEAR.fullmatch(value) else "")
        if value:
            groups.setdefault(unit, set()).add(value)
    return groups
