"""Application settings and persisted provider configuration.

Provider credentials are stored server-side only (``data/settings.json``) and
are never returned to the client in clear text.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("AIPODCASTER_DATA_DIR", ROOT_DIR / "data")).resolve()
MAX_UPLOAD_BYTES = int(os.environ.get("AIPODCASTER_MAX_UPLOAD_MB", "8192")) * 1024 * 1024
MAX_DURATION_SECONDS = int(os.environ.get("AIPODCASTER_MAX_DURATION_MIN", "600")) * 60
ALLOW_LOCAL_IMPORT = os.environ.get("AIPODCASTER_ALLOW_LOCAL_IMPORT", "1") not in {"0", "false", "no"}
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("AIPODCASTER_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]
SECRET_MASK = "••••••••"


class TranscriptionSettings(BaseModel):
    provider: str = Field(default="faster_whisper", pattern="^(faster_whisper|openai|fake)$")
    model: str = Field(default="small", max_length=100)
    language: str | None = Field(default=None, max_length=10)


class LanguageModelSettings(BaseModel):
    provider: str = Field(default="none", pattern="^(none|openai|anthropic|gemini|ollama|openai_compatible)$")
    model: str = Field(default="", max_length=100)
    base_url: str = Field(default="", max_length=300)
    temperature: float = Field(default=0.2, ge=0, le=2)


class SpeechSettings(BaseModel):
    provider: str = Field(default="none", pattern="^(none|openai|elevenlabs|descript|custom_http)$")
    voice: str = Field(default="alloy", max_length=200)
    model: str = Field(default="", max_length=100)
    base_url: str = Field(default="", max_length=300)
    custom_body_template: str = Field(default='{"text": "{text}", "voice": "{voice}"}', max_length=4_000)
    custom_auth_header: str = Field(default="Authorization: Bearer {key}", max_length=200)


class ImageSettings(BaseModel):
    provider: str = Field(default="none", pattern="^(none|openai)$")
    model: str = Field(default="gpt-image-1", max_length=100)


class ApiAccessSettings(BaseModel):
    """Keys that external clients (scripts, MCP server) must present as X-API-Key."""

    keys: list[str] = Field(default_factory=list, max_length=20)
    require_for_ui: bool = False


class CleanupSettings(BaseModel):
    remove_profanity: bool = True
    remove_fillers: bool = True
    remove_repeats: bool = True
    tighten_silence: bool = True
    max_pause_ms: int = Field(default=1500, ge=300, le=10_000)
    keep_pause_ms: int = Field(default=350, ge=100, le=2_000)
    extra_bad_words: list[str] = Field(default_factory=list, max_length=500)
    extra_filler_words: list[str] = Field(default_factory=list, max_length=200)
    target_lufs: float = Field(default=-16.0, ge=-30, le=-8)


class FactCheckSettings(BaseModel):
    embedding_provider: str = Field(default="local", pattern="^(local|openai)$")
    embedding_model: str = Field(default="text-embedding-3-small", max_length=100)
    online_enabled: bool = True
    wikipedia_language: str = Field(default="en", max_length=10, pattern="^[a-z-]+$")
    max_claims: int = Field(default=40, ge=1, le=200)
    evidence_per_claim: int = Field(default=4, ge=1, le=10)
    min_similarity: float = Field(default=0.35, ge=0, le=1)


class ProviderKeys(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    elevenlabs_api_key: str = ""
    descript_api_key: str = ""
    custom_llm_api_key: str = ""
    custom_tts_api_key: str = ""


class AppSettings(BaseModel):
    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    language_model: LanguageModelSettings = Field(default_factory=LanguageModelSettings)
    speech: SpeechSettings = Field(default_factory=SpeechSettings)
    cleanup: CleanupSettings = Field(default_factory=CleanupSettings)
    fact_check: FactCheckSettings = Field(default_factory=FactCheckSettings)
    api: ApiAccessSettings = Field(default_factory=ApiAccessSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    keys: ProviderKeys = Field(default_factory=ProviderKeys)

    def masked(self) -> dict:
        """Return a client-safe view where secrets are replaced by a mask."""
        data = self.model_dump()
        data["keys"] = {name: (SECRET_MASK if value else "") for name, value in self.keys.model_dump().items()}
        data["api"]["keys"] = [f"{key[:8]}…" for key in self.api.keys]
        return data

    def merge_keys(self, incoming: ProviderKeys) -> ProviderKeys:
        """Keep an existing secret when the client sends back the mask."""
        current = self.keys.model_dump()
        for name, value in incoming.model_dump().items():
            if value == SECRET_MASK:
                continue
            current[name] = value.strip()
        return ProviderKeys(**current)


OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = f"http://{OLLAMA_URL}"


class SettingsStore:
    """Thread-safe JSON-backed settings with environment variable fallbacks."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._settings = self._load()

    def _load(self) -> AppSettings:
        settings = AppSettings()
        if self._path.exists():
            try:
                settings = AppSettings.model_validate(json.loads(self._path.read_text("utf-8")))
            except (ValueError, OSError):
                settings = AppSettings()
        keys = settings.keys
        settings.keys = ProviderKeys(
            openai_api_key=keys.openai_api_key or os.environ.get("OPENAI_API_KEY", ""),
            anthropic_api_key=keys.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            gemini_api_key=keys.gemini_api_key or os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")),
            elevenlabs_api_key=keys.elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY", ""),
            descript_api_key=keys.descript_api_key or os.environ.get("DESCRIPT_API_KEY", ""),
            custom_llm_api_key=keys.custom_llm_api_key,
            custom_tts_api_key=keys.custom_tts_api_key,
        )
        env_keys = [k.strip() for k in os.environ.get("AIPODCASTER_API_KEYS", "").split(",") if k.strip()]
        settings.api.keys = list(dict.fromkeys(settings.api.keys + env_keys))
        if os.environ.get("AIPODCASTER_TRANSCRIBER"):
            settings.transcription.provider = os.environ["AIPODCASTER_TRANSCRIBER"]
        return settings

    def get(self) -> AppSettings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def mutate(self, fn) -> AppSettings:  # noqa: ANN001 - callable(AppSettings) -> None
        """Apply an in-place change under the lock and persist (used for API keys and Ollama setup)."""
        with self._lock:
            fn(self._settings)
            self._persist(self._settings)
            return self._settings.model_copy(deep=True)

    def _persist(self, settings: AppSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(settings.model_dump(), indent=2), "utf-8")
        tmp.replace(self._path)

    def update(self, incoming: AppSettings) -> AppSettings:
        with self._lock:
            incoming.keys = self._settings.merge_keys(incoming.keys)
            incoming.api.keys = list(self._settings.api.keys)  # managed only via /v1/api-keys
            self._settings = incoming
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(incoming.model_dump(), indent=2), "utf-8")
            tmp.replace(self._path)
            return self._settings.model_copy(deep=True)


settings_store = SettingsStore(DATA_DIR / "settings.json")
