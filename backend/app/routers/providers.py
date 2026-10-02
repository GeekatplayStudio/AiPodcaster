"""Provider catalog, Ollama management, connection tests, voice cloning, API keys."""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..config import settings_store
from ..providers import llm, ollama, voice
from ..security import generate_key
from ..services import pipeline
from ..storage import job_store

router = APIRouter(prefix="/v1/providers", tags=["providers"])
keys_router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


class OllamaSetupRequest(BaseModel):
    model: str | None = Field(default=None, max_length=120)
    start_server: bool = True


class CloneRequest(BaseModel):
    job_id: UUID
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    set_as_default: bool = True


class ApiKeyCreate(BaseModel):
    label: str = Field(default="", max_length=60)


@router.get("/catalog")
async def catalog() -> dict:
    settings = settings_store.get()
    keys = settings.keys.model_dump()
    return {
        "llm": [{**asdict(p), "configured": (not p.needs_key) or bool(keys.get(p.key_field))} for p in llm.CATALOG],
        "speech": [{**asdict(p), "configured": (not p.key_field) or bool(keys.get(p.key_field))} for p in voice.VOICE_CATALOG],
        "current_llm": {"provider": settings.language_model.provider, "model": llm.model_for(settings), "configured": llm.is_configured(settings)},
        "current_speech": settings.speech.provider,
    }


@router.post("/llm/test")
async def test_llm() -> dict:
    settings = settings_store.get()
    try:
        return await run_in_threadpool(llm.test_connection, settings)
    except llm.LLMError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/ollama/status")
async def ollama_status() -> dict:
    return await run_in_threadpool(ollama.status, settings_store.get())


@router.post("/ollama/setup")
async def ollama_setup(body: OllamaSetupRequest) -> dict:
    result = await run_in_threadpool(ollama.setup, body.model, body.start_server)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("message", "Ollama setup failed"))
    return result


@router.post("/ollama/start")
async def ollama_start() -> dict:
    started = await run_in_threadpool(ollama.try_start_server)
    if not started:
        raise HTTPException(status_code=503, detail="Ollama could not be started. Install it from https://ollama.com")
    return {"running": True}


@router.post("/voice/clone")
async def clone_voice(body: CloneRequest) -> dict:
    settings = settings_store.get()
    if settings.speech.provider != "elevenlabs":
        raise HTTPException(status_code=422, detail="Voice cloning is currently supported for ElevenLabs. Select it as the speech provider first.")
    job_store.get(body.job_id)
    sample = pipeline.canonical_wav(job_store, body.job_id)
    if not sample.exists():
        raise HTTPException(status_code=409, detail="The episode audio is not ready yet")
    try:
        result = await run_in_threadpool(voice.clone_voice_elevenlabs, settings, body.name, sample, body.description)
    except voice.SpeechError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    if body.set_as_default and result["voice_id"]:
        settings_store.mutate(lambda s: setattr(s.speech, "voice", result["voice_id"]))
    return result


@keys_router.get("")
async def list_keys() -> list[dict]:
    return [{"prefix": key[:8], "hint": f"{key[:8]}…{key[-4:]}"} for key in settings_store.get().api.keys]


@keys_router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(body: ApiKeyCreate) -> dict:
    """Generate a key. The full value is shown once; store it safely."""
    key = generate_key()
    settings_store.mutate(lambda s: s.api.keys.append(key))
    return {"key": key, "prefix": key[:8], "label": body.label, "header": "X-API-Key"}


@keys_router.delete("/{prefix}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(prefix: str) -> None:
    current = settings_store.get().api.keys
    if not any(key.startswith(prefix) for key in current):
        raise HTTPException(status_code=404, detail="Key not found")
    settings_store.mutate(lambda s: s.api.keys.__init__([key for key in s.api.keys if not key.startswith(prefix)]))
