"""Transcription providers behind one interface.

* ``faster_whisper`` – local CTranslate2 Whisper (GPU when available).
* ``openai`` – OpenAI hosted transcription with word timestamps.
* ``fake`` – deterministic provider for automated tests (never used unless
  explicitly configured).
"""
from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import AppSettings
from ..schemas import TranscriptSegment, Word
from . import languages

log = logging.getLogger("aipodcaster.transcription")


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str | None
    provider: str


class TranscriptionProvider(Protocol):
    name: str

    def transcribe(self, wav_16k: Path) -> TranscriptionResult: ...


class TranscriptionError(RuntimeError):
    pass


def _segments_from_words(words: list[Word], max_gap_ms: int = 900, max_words: int = 28) -> list[TranscriptSegment]:
    """Group words into sentence-like segments using punctuation and pauses."""
    segments: list[TranscriptSegment] = []
    bucket: list[Word] = []

    def flush() -> None:
        if not bucket:
            return
        segments.append(
            TranscriptSegment(
                id=len(segments),
                start_ms=bucket[0].start_ms,
                end_ms=bucket[-1].end_ms,
                text=" ".join(word.text for word in bucket).strip(),
                words=list(bucket),
            )
        )
        bucket.clear()

    for word in words:
        if bucket and (word.start_ms - bucket[-1].end_ms > max_gap_ms or len(bucket) >= max_words):
            flush()
        bucket.append(word)
        if word.text.rstrip().endswith((".", "?", "!")) and len(bucket) >= 4:
            flush()
    flush()
    return segments


class FasterWhisperProvider:
    name = "faster_whisper"

    def __init__(self, model_size: str, language: str | None, verbatim: bool = True) -> None:
        self._model_size = model_size or "small"
        self._language = language
        self._verbatim = verbatim

    def _run(self, model, audio):  # noqa: ANN001
        language = self._language
        if self._verbatim and not language:
            try:
                language, _, _ = model.detect_language(audio, vad_filter=True, language_detection_segments=3)
            except Exception:  # noqa: BLE001 - detection is only a hint for the prompt
                language = None
        prompt = languages.verbatim_prompt(language) if self._verbatim else None
        return model.transcribe(audio, language=self._language or language, word_timestamps=True, vad_filter=True, beam_size=5, initial_prompt=prompt)

    def transcribe(self, wav_16k: Path) -> TranscriptionResult:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise TranscriptionError("faster-whisper is not installed. Run pip install faster-whisper or choose another provider.") from error
        audio = _read_wav_16k(wav_16k)
        try:
            model = _load_model(WhisperModel, self._model_size)
            raw_segments, info = self._run(model, audio)
        except RuntimeError as error:
            if not _looks_like_gpu_problem(error):
                raise TranscriptionError(f"Transcription failed: {error}") from error
            log.warning("GPU transcription unavailable (%s); falling back to CPU", str(error)[:120])
            model = _load_model(WhisperModel, self._model_size, force_cpu=True)
            raw_segments, info = self._run(model, audio)
        words: list[Word] = []
        for segment in raw_segments:
            for word in segment.words or []:
                text = word.word.strip()
                if text:
                    words.append(Word(text=text, start_ms=int(word.start * 1000), end_ms=int(word.end * 1000), confidence=max(0.0, min(1.0, float(word.probability)))))
        return TranscriptionResult(segments=_segments_from_words(words), language=getattr(info, "language", None), provider=self.name)


_model_cache: dict[str, object] = {}


def _read_wav_16k(path: Path):
    """Decode the canonical 16 kHz mono PCM WAV without relying on PyAV."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
            raise TranscriptionError("Expected 16-bit mono WAV for transcription")
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _looks_like_gpu_problem(error: Exception) -> bool:
    text = str(error).lower()
    return any(token in text for token in ("cublas", "cudnn", "cuda", "cannot be loaded", "libcu", "device"))


def _register_cuda_dlls() -> None:
    """Make the optional nvidia-* pip wheels (cuBLAS, cuDNN) loadable on Windows."""
    import os
    import sys

    if not hasattr(os, "add_dll_directory"):
        return
    for base in sys.path:
        nvidia = Path(base) / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in nvidia.glob("*/bin"):
            try:
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
            except OSError:
                continue


def _load_model(model_class, size: str, force_cpu: bool = False):
    key = f"{size}:{'cpu' if force_cpu else 'auto'}"
    if key in _model_cache:
        return _model_cache[key]
    _register_cuda_dlls()
    model = None
    if not force_cpu:
        try:
            model = model_class(size, device="cuda", compute_type="float16")
        except Exception:  # noqa: BLE001 - any CUDA failure falls back to CPU
            model = None
    if model is None:
        model = model_class(size, device="cpu", compute_type="int8")
    _model_cache[key] = model
    return model


class OpenAITranscriptionProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, language: str | None, verbatim: bool = True) -> None:
        if not api_key:
            raise TranscriptionError("OpenAI API key is not configured")
        self._api_key = api_key
        self._model = model or "whisper-1"
        self._language = language
        self._verbatim = verbatim

    def transcribe(self, wav_16k: Path) -> TranscriptionResult:
        import httpx

        files = {"file": (wav_16k.name, wav_16k.read_bytes(), "audio/wav")}
        data: dict[str, str] = {"model": self._model, "response_format": "verbose_json", "timestamp_granularities[]": "word"}
        if self._language:
            data["language"] = self._language
        if self._verbatim:
            data["prompt"] = languages.verbatim_prompt(self._language)
        response = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            data=data,
            files=files,
            timeout=600,
        )
        if response.status_code >= 400:
            raise TranscriptionError(f"OpenAI transcription failed ({response.status_code})")
        payload = response.json()
        words = [
            Word(text=str(item["word"]).strip(), start_ms=int(float(item["start"]) * 1000), end_ms=int(float(item["end"]) * 1000))
            for item in payload.get("words", [])
            if str(item.get("word", "")).strip()
        ]
        if not words:
            for segment in payload.get("segments", []):
                words.append(Word(text=str(segment["text"]).strip(), start_ms=int(float(segment["start"]) * 1000), end_ms=int(float(segment["end"]) * 1000)))
        return TranscriptionResult(segments=_segments_from_words(words), language=payload.get("language"), provider=self.name)


class FakeTranscriptionProvider:
    """Deterministic transcript used by the automated test-suite."""

    name = "fake"
    script = "Welcome back to the show. Um, today we we talk about building better habits. Damn, that is a big topic. So let's get started."

    def transcribe(self, wav_16k: Path) -> TranscriptionResult:
        words: list[Word] = []
        cursor = 400
        for token in self.script.split():
            length = 180 + 40 * len(token)
            words.append(Word(text=token, start_ms=cursor, end_ms=cursor + length))
            cursor += length + (1800 if token.endswith(".") else 90)
        return TranscriptionResult(segments=_segments_from_words(words), language="en", provider=self.name)


def build_provider(settings: AppSettings, language_override: str | None = None) -> TranscriptionProvider:
    config = settings.transcription
    language = language_override or config.language
    if config.provider == "fake":
        return FakeTranscriptionProvider()
    if config.provider == "openai":
        return OpenAITranscriptionProvider(settings.keys.openai_api_key, config.model, language, config.verbatim)
    return FasterWhisperProvider(config.model, language, config.verbatim)


def provider_status(settings: AppSettings) -> list[dict[str, str | bool]]:
    local = importlib.util.find_spec("faster_whisper") is not None
    return [
        {"name": "faster_whisper", "available": local, "detail": "Local Whisper (free, private)" if local else "pip install faster-whisper"},
        {"name": "openai", "available": bool(settings.keys.openai_api_key), "detail": "Uses OpenAI API key"},
    ]
