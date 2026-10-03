"""Turn pasted or uploaded text (transcript, script, article) into transcript segments.

Recognises SRT / WebVTT captions, timestamped transcripts ("[00:12]", "00:01:05"),
speaker-labelled dialogue ("HOST: ...") and plain prose. Timing is estimated from
a words-per-minute rate so the review tools and synthetic voice work unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import TranscriptSegment, Word

TIMESTAMP = re.compile(r"^\s*[\[(]?(?P<h>\d{1,2}:)?(?P<m>\d{1,2}):(?P<s>\d{2})(?:[.,]\d{1,3})?[\])]?\s*[-–—:]?\s*")
SRT_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
SPEAKER = re.compile(r"^\s*(?:\[[^\]]+\]\s*)?([A-ZÀ-ÖØ-ÞА-ЯЁІЇЄҐΑ-Ω][\w ._'-]{0,30}):\s+(?=\S)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
MAX_WORDS_PER_SEGMENT = 40


@dataclass
class DetectedText:
    format: str  # srt | vtt | timestamped | dialogue | prose
    segments: list[TranscriptSegment]
    speakers: list[str]
    word_count: int
    estimated_duration_ms: int


def detect_format(text: str) -> str:
    head = text.lstrip()[:4000]
    if head.startswith("WEBVTT"):
        return "vtt"
    if SRT_TIME.search(head):
        return "srt"
    lines = [line for line in head.splitlines() if line.strip()][:40]
    if lines:
        stamped = sum(1 for line in lines if TIMESTAMP.match(line) and TIMESTAMP.match(line).group("m"))
        if stamped >= max(2, len(lines) // 3):
            return "timestamped"
        spoken = sum(1 for line in lines if SPEAKER.match(line))
        if spoken >= max(2, len(lines) // 3):
            return "dialogue"
    return "prose"


def _to_ms(h: str | None, m: str, s: str) -> int:
    hours = int(h.rstrip(":")) if h else 0
    return (hours * 3600 + int(m) * 60 + int(s)) * 1000


def _words(text: str, start_ms: int, end_ms: int) -> list[Word]:
    tokens = text.split()
    if not tokens:
        return []
    span = max(end_ms - start_ms, len(tokens) * 50)
    step = span / len(tokens)
    return [Word(text=token, start_ms=int(start_ms + index * step), end_ms=int(start_ms + (index + 1) * step) - 20) for index, token in enumerate(tokens)]


def _chunks(text: str, limit: int = MAX_WORDS_PER_SEGMENT) -> list[str]:
    """Sentence-aware chunks so segments stay reviewable."""
    out: list[str] = []
    current: list[str] = []
    for sentence in SENTENCE_SPLIT.split(text.strip()):
        words = sentence.split()
        if not words:
            continue
        if current and len(current) + len(words) > limit:
            out.append(" ".join(current))
            current = []
        if len(words) > limit:
            for start in range(0, len(words), limit):
                out.append(" ".join(words[start : start + limit]))
            continue
        current.extend(words)
    if current:
        out.append(" ".join(current))
    return out


def _parse_captions(text: str) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    current: tuple[int, int] | None = None
    buffer: list[str] = []
    for raw in text.splitlines() + [""]:
        line = raw.strip()
        match = SRT_TIME.search(line)
        if match:
            if current and buffer:
                blocks.append((*current, " ".join(buffer)))
            h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(value) for value in match.groups())
            current = ((h1 * 3600 + m1 * 60 + s1) * 1000 + ms1, (h2 * 3600 + m2 * 60 + s2) * 1000 + ms2)
            buffer = []
        elif not line:
            if current and buffer:
                blocks.append((*current, " ".join(buffer)))
            current, buffer = None, []
        elif current is not None and not line.isdigit():
            buffer.append(re.sub(r"<[^>]+>", "", line))
    return blocks


def _parse_timestamped(text: str) -> list[tuple[int, str, str | None]]:
    rows: list[tuple[int, str, str | None]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = TIMESTAMP.match(line)
        if match and match.group("m"):
            start = _to_ms(match.group("h"), match.group("m"), match.group("s"))
            rest = line[match.end() :]
            speaker = None
            label = SPEAKER.match(rest)
            if label:
                speaker, rest = label.group(1).strip(), rest[label.end() :]
            rows.append((start, rest.strip(), speaker))
        elif rows:
            start, previous, speaker = rows[-1]
            rows[-1] = (start, f"{previous} {line}".strip(), speaker)
    return rows


def _parse_dialogue(text: str) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = SPEAKER.match(line)
        if match:
            rows.append((line[match.end() :].strip(), match.group(1).strip()))
        elif rows:
            rows[-1] = (f"{rows[-1][0]} {line}", rows[-1][1])
        else:
            rows.append((line, None))
    return rows


def build_segments(text: str, words_per_minute: int = 150) -> DetectedText:
    text = text.replace("\r\n", "\n").replace("\x00", "").strip()
    ms_per_word = 60_000 / max(words_per_minute, 60)
    fmt = detect_format(text)
    segments: list[TranscriptSegment] = []
    speakers: list[str] = []

    def add(start: int, body: str, speaker: str | None = None, end: int | None = None) -> int:
        body = " ".join(body.split())
        if not body:
            return start
        if speaker and speaker not in speakers:
            speakers.append(speaker)
        duration = end - start if end and end > start else int(len(body.split()) * ms_per_word)
        prefix = f"{speaker}: " if speaker else ""
        words = _words(body, start, start + duration)
        segments.append(TranscriptSegment(id=len(segments), start_ms=start, end_ms=start + duration, text=prefix + body, words=words))
        return start + duration + 400

    if fmt in {"srt", "vtt"}:
        for start, end, body in _parse_captions(text):
            add(start, body, None, end)
    elif fmt == "timestamped":
        rows = _parse_timestamped(text)
        for index, (start, body, speaker) in enumerate(rows):
            next_start = rows[index + 1][0] if index + 1 < len(rows) else None
            add(start, body, speaker, next_start if next_start and next_start > start else None)
    elif fmt == "dialogue":
        cursor = 0
        for body, speaker in _parse_dialogue(text):
            for chunk in _chunks(body):
                cursor = add(cursor, chunk, speaker)
    else:
        cursor = 0
        for paragraph in re.split(r"\n\s*\n", text):
            for chunk in _chunks(paragraph.replace("\n", " ")):
                cursor = add(cursor, chunk)
    word_count = sum(len(segment.words) for segment in segments)
    duration = max((segment.end_ms for segment in segments), default=0)
    return DetectedText(format=fmt, segments=segments, speakers=speakers, word_count=word_count, estimated_duration_ms=duration)


def strip_speaker_labels(segments: list[TranscriptSegment]) -> str:
    """Plain spoken text for text-to-speech (labels like "HOST:" are not read aloud)."""
    parts = []
    for segment in segments:
        parts.append(SPEAKER.sub("", segment.text, count=1))
    return " ".join(parts)
