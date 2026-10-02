"""Text-to-speech providers for the opt-in synthetic voice mode."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..providers import voice as _voice

SpeechError = _voice.SpeechError

MAX_CHUNK_CHARS = 3_500


class SpeechProvider(Protocol):
    name: str

    def synthesize(self, text: str, target: Path) -> Path: ...


def chunk_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on sentence boundaries so provider limits are respected."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        piece = sentence if sentence.endswith((".", "!", "?")) else sentence + "."
        if len(current) + len(piece) + 1 > limit and current:
            chunks.append(current.strip())
            current = ""
        current += " " + piece
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text[:limit]]


build_speech_provider = _voice.build_speech_provider
