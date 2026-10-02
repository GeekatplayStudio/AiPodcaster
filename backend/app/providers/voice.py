"""Speech synthesis and voice-cloning providers.

* OpenAI TTS, ElevenLabs (with instant voice cloning from an episode's own
  recording), Descript and any custom HTTP endpoint (JSON in, audio out).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..config import AppSettings


class SpeechError(RuntimeError):
    pass


class SpeechProvider(Protocol):
    name: str

    def synthesize(self, text: str, target: Path) -> Path: ...


@dataclass(frozen=True)
class VoiceProviderInfo:
    id: str
    label: str
    key_field: str
    default_model: str
    default_base_url: str
    supports_cloning: bool
    notes: str


VOICE_CATALOG: list[VoiceProviderInfo] = [
    VoiceProviderInfo("none", "Disabled (keep original voice)", "", "", "", False, ""),
    VoiceProviderInfo("openai", "OpenAI text-to-speech", "openai_api_key", "gpt-4o-mini-tts", "https://api.openai.com/v1", False, "Voices: alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer."),
    VoiceProviderInfo("elevenlabs", "ElevenLabs", "elevenlabs_api_key", "eleven_multilingual_v2", "https://api.elevenlabs.io", True, "Voice = voice_id. Use “Clone my voice” on an episode to create one from your own recording."),
    VoiceProviderInfo("descript", "Descript (Overdub)", "descript_api_key", "", "https://api.descript.com", True, "Requires Descript API access; set the base URL given by Descript and your Overdub voice id."),
    VoiceProviderInfo("custom_http", "Custom HTTP endpoint", "custom_tts_api_key", "", "", False, "POST a JSON body template with {text}/{voice}/{model}; the response body must be audio."),
]


def _post_audio(url: str, headers: dict[str, str], payload: dict, target: Path, provider: str) -> Path:
    import httpx

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=300)
    except httpx.HTTPError as error:
        raise SpeechError(f"{provider}: could not reach {url}: {error}") from error
    if response.status_code >= 400:
        raise SpeechError(f"{provider} speech failed ({response.status_code}): {response.text[:200]}")
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        raise SpeechError(f"{provider} returned JSON instead of audio: {response.text[:200]}")
    target.write_bytes(response.content)
    return target


class OpenAISpeech:
    name = "openai"

    def __init__(self, settings: AppSettings) -> None:
        if not settings.keys.openai_api_key:
            raise SpeechError("OpenAI API key is not configured")
        self._key, self._voice = settings.keys.openai_api_key, settings.speech.voice or "alloy"
        self._model = settings.speech.model or "gpt-4o-mini-tts"
        self._base = (settings.speech.base_url or "https://api.openai.com/v1").rstrip("/")

    def synthesize(self, text: str, target: Path) -> Path:
        return _post_audio(f"{self._base}/audio/speech", {"Authorization": f"Bearer {self._key}"}, {"model": self._model, "voice": self._voice, "input": text, "response_format": "mp3"}, target, "OpenAI")


class ElevenLabsSpeech:
    name = "elevenlabs"

    def __init__(self, settings: AppSettings) -> None:
        if not settings.keys.elevenlabs_api_key:
            raise SpeechError("ElevenLabs API key is not configured")
        self._key, self._voice = settings.keys.elevenlabs_api_key, settings.speech.voice or "21m00Tcm4TlvDq8ikWAM"
        self._model = settings.speech.model or "eleven_multilingual_v2"
        self._base = (settings.speech.base_url or "https://api.elevenlabs.io").rstrip("/")

    def synthesize(self, text: str, target: Path) -> Path:
        return _post_audio(f"{self._base}/v1/text-to-speech/{self._voice}", {"xi-api-key": self._key, "accept": "audio/mpeg"}, {"text": text, "model_id": self._model}, target, "ElevenLabs")


class DescriptSpeech:
    """Descript Overdub adapter. Descript's API is partner-gated, so the base URL and
    payload follow their documented JSON shape and are configurable."""

    name = "descript"

    def __init__(self, settings: AppSettings) -> None:
        if not settings.keys.descript_api_key:
            raise SpeechError("Descript API key is not configured")
        if not settings.speech.voice:
            raise SpeechError("Descript Overdub voice id is required")
        self._key, self._voice = settings.keys.descript_api_key, settings.speech.voice
        self._base = (settings.speech.base_url or "https://api.descript.com").rstrip("/")

    def synthesize(self, text: str, target: Path) -> Path:
        return _post_audio(f"{self._base}/v1/overdub/synthesize", {"Authorization": f"Bearer {self._key}"}, {"voice_id": self._voice, "text": text, "format": "mp3"}, target, "Descript")


class CustomHttpSpeech:
    name = "custom_http"

    def __init__(self, settings: AppSettings) -> None:
        if not settings.speech.base_url:
            raise SpeechError("Custom speech endpoint URL is required")
        self._url = settings.speech.base_url
        self._template = settings.speech.custom_body_template
        self._voice, self._model, self._key = settings.speech.voice, settings.speech.model, settings.keys.custom_tts_api_key
        self._auth = settings.speech.custom_auth_header

    def synthesize(self, text: str, target: Path) -> Path:
        body = self._template.replace("{text}", json.dumps(text)[1:-1]).replace("{voice}", self._voice).replace("{model}", self._model)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise SpeechError("Custom body template is not valid JSON after substitution") from error
        headers: dict[str, str] = {}
        if self._key and ":" in self._auth:
            name, value = self._auth.split(":", 1)
            headers[name.strip()] = value.strip().replace("{key}", self._key)
        return _post_audio(self._url, headers, payload, target, "Custom endpoint")


def build_speech_provider(settings: AppSettings) -> SpeechProvider:
    provider = settings.speech.provider
    builders = {"openai": OpenAISpeech, "elevenlabs": ElevenLabsSpeech, "descript": DescriptSpeech, "custom_http": CustomHttpSpeech}
    if provider not in builders:
        raise SpeechError("No speech provider configured. Choose one in Settings, or use original voice.")
    return builders[provider](settings)


def clone_voice_elevenlabs(settings: AppSettings, name: str, sample: Path, description: str = "") -> dict:
    """Create an ElevenLabs instant voice clone from a WAV/MP3 sample; returns {voice_id, name}."""
    import httpx

    key = settings.keys.elevenlabs_api_key
    if not key:
        raise SpeechError("ElevenLabs API key is not configured")
    base = (settings.speech.base_url or "https://api.elevenlabs.io").rstrip("/")
    with sample.open("rb") as handle:
        response = httpx.post(
            f"{base}/v1/voices/add",
            headers={"xi-api-key": key},
            data={"name": name[:100], "description": description[:500], "remove_background_noise": "true"},
            files={"files": (sample.name, handle, "audio/wav")},
            timeout=600,
        )
    if response.status_code >= 400:
        raise SpeechError(f"ElevenLabs voice clone failed ({response.status_code}): {response.text[:200]}")
    data = response.json()
    return {"voice_id": str(data.get("voice_id", "")), "name": name}
