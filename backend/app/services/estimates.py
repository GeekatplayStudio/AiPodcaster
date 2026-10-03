"""Rough processing-time estimates so users know what to expect for long recordings.

Figures are seconds of processing per second of audio (real-time factor),
measured on typical hardware and deliberately on the conservative side.
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache

from ..config import AppSettings

WHISPER_RTF = {
    "gpu": {"tiny": 0.02, "base": 0.03, "small": 0.05, "medium": 0.10, "large-v3": 0.15, "distil-large-v3": 0.08},
    "cpu": {"tiny": 0.12, "base": 0.20, "small": 0.50, "medium": 1.20, "large-v3": 2.50, "distil-large-v3": 1.00},
}
PREP_RTF = 0.03  # FFmpeg conversion, loudness and silence analysis
RENDER_RTF = 0.04  # cutting, mastering, MP3 export
LLM_SECONDS = {"none": 0, "ollama": 90, "anthropic": 20, "openai": 20, "gemini": 20, "openai_compatible": 60}
LONG_RECORDING_SECONDS = 30 * 60


@lru_cache(maxsize=1)
def gpu_available() -> bool:
    if importlib.util.find_spec("ctranslate2") is None:
        return False
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def device() -> str:
    return "gpu" if gpu_available() else "cpu"


def transcription_rtf(settings: AppSettings) -> float:
    config = settings.transcription
    if config.provider == "fake":
        return 0.0
    if config.provider == "openai":
        return 0.08
    table = WHISPER_RTF[device()]
    return table.get(config.model, table["small"])


def analysis_seconds(settings: AppSettings, duration_s: float) -> int:
    """Upload-to-review time: preparation, transcription, cleanup analysis and show notes."""
    rtf = PREP_RTF + transcription_rtf(settings)
    return int(duration_s * rtf + LLM_SECONDS.get(settings.language_model.provider, 30) + 5)


def render_seconds(settings: AppSettings, duration_s: float, synthetic: bool) -> int:
    tts = duration_s * 0.15 if synthetic else 0
    return int(duration_s * RENDER_RTF + tts + 5)


def describe(settings: AppSettings) -> dict:
    """Numbers the client uses to warn before uploading a long file."""
    return {
        "device": device(),
        "transcription_provider": settings.transcription.provider,
        "transcription_model": settings.transcription.model,
        "analysis_rtf": round(PREP_RTF + transcription_rtf(settings), 3),
        "llm_seconds": LLM_SECONDS.get(settings.language_model.provider, 30),
        "render_rtf": RENDER_RTF,
        "long_recording_seconds": LONG_RECORDING_SECONDS,
    }
