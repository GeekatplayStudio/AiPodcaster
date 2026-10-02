"""Provider configuration endpoints. Secrets are masked on the way out."""
from __future__ import annotations

import importlib.util

from fastapi import APIRouter

from ..config import AppSettings, settings_store
from ..providers import llm, ollama
from ..schemas import ProviderStatus
from ..services import audio
from ..services.transcription import provider_status

router = APIRouter(prefix="/v1/settings", tags=["settings"])


@router.get("")
async def get_settings() -> dict:
    return settings_store.get().masked()


@router.put("")
async def update_settings(incoming: AppSettings) -> dict:
    return settings_store.update(incoming).masked()


@router.get("/providers", response_model=list[ProviderStatus])
async def providers() -> list[ProviderStatus]:
    settings = settings_store.get()
    keys = settings.keys
    items = [ProviderStatus(**item) for item in provider_status(settings)]
    items += [
        ProviderStatus(name="ffmpeg", available=audio.tools_available(), detail="Required for all audio processing"),
        ProviderStatus(name="cuda", available=_cuda(), detail="GPU acceleration for local Whisper"),
        ProviderStatus(name="language_model", available=llm.is_configured(settings), detail=f"{settings.language_model.provider} / {llm.model_for(settings) or 'no model'}"),
        ProviderStatus(name="ollama", available=ollama.is_running(ollama.base_url(settings)), detail="Local LLM server"),
        ProviderStatus(name="openai", available=bool(keys.openai_api_key), detail="LLM, transcription, TTS"),
        ProviderStatus(name="anthropic", available=bool(keys.anthropic_api_key), detail="Claude LLM"),
        ProviderStatus(name="gemini", available=bool(keys.gemini_api_key), detail="Gemini LLM"),
        ProviderStatus(name="elevenlabs", available=bool(keys.elevenlabs_api_key), detail="TTS + voice cloning"),
        ProviderStatus(name="descript", available=bool(keys.descript_api_key), detail="Overdub voice"),
        ProviderStatus(name="api_keys", available=bool(settings.api.keys), detail=f"{len(settings.api.keys)} external API key(s); MCP server uses these"),
        ProviderStatus(name="vector_index", available=importlib.util.find_spec("chromadb") is not None, detail="ChromaDB + local MiniLM embeddings for libraries"),
        ProviderStatus(name="document_parsers", available=importlib.util.find_spec("pypdf") is not None and importlib.util.find_spec("docx") is not None, detail="PDF / DOCX / EPUB / text import"),
    ]
    return items


def _cuda() -> bool:
    if importlib.util.find_spec("ctranslate2") is None:
        return False
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False
