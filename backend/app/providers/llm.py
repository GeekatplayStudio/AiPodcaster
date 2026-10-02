"""One `complete()` entry point for every language-model backend.

Supported: OpenAI, Anthropic Claude, Google Gemini, Ollama (local) and any
OpenAI-compatible server (LM Studio, vLLM, Groq, OpenRouter, Mistral, ...).
All calls use plain HTTPS via httpx; no vendor SDKs are required.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import OLLAMA_URL, AppSettings

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-2.5-flash",
    "ollama": "",  # chosen by providers.ollama.recommend()
    "openai_compatible": "",
}


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    needs_key: bool
    key_field: str
    default_model: str
    default_base_url: str
    notes: str


CATALOG: list[ProviderInfo] = [
    ProviderInfo("none", "Built-in heuristics (offline)", False, "", "", "", "No model; keyword/number heuristics only."),
    ProviderInfo("ollama", "Ollama (local)", False, "", "", OLLAMA_URL, "Runs on this machine. AiPodcaster can pick, pull and warm up the best model."),
    ProviderInfo("anthropic", "Anthropic Claude", True, "anthropic_api_key", DEFAULT_MODELS["anthropic"], "https://api.anthropic.com", "Messages API."),
    ProviderInfo("openai", "OpenAI (ChatGPT models)", True, "openai_api_key", DEFAULT_MODELS["openai"], "https://api.openai.com/v1", "Chat Completions API."),
    ProviderInfo("gemini", "Google Gemini", True, "gemini_api_key", DEFAULT_MODELS["gemini"], "https://generativelanguage.googleapis.com/v1beta", "Gemini generateContent API."),
    ProviderInfo("openai_compatible", "OpenAI-compatible server", False, "custom_llm_api_key", "", "http://localhost:1234/v1", "LM Studio, vLLM, Groq, OpenRouter, Mistral, DeepSeek ... set the base URL and model."),
]


def _timeout(settings: AppSettings) -> float:
    return 300.0 if settings.language_model.provider == "ollama" else 120.0


def _base(settings: AppSettings, default: str) -> str:
    return (settings.language_model.base_url or default).rstrip("/")


def _post(url: str, headers: dict[str, str], payload: dict, timeout: float) -> dict:
    import httpx

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.HTTPError as error:
        raise LLMError(f"Could not reach {url.split('/v1')[0]}: {error}") from error
    if response.status_code >= 400:
        raise LLMError(f"{url} returned {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError as error:
        raise LLMError("Model returned a non-JSON response") from error


def _openai_style(settings: AppSettings, prompt: str, base_url: str, api_key: str, model: str, json_mode: bool, system: str | None) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    payload: dict = {"model": model, "messages": messages, "temperature": settings.language_model.temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    data = _post(f"{base_url}/chat/completions", headers, payload, _timeout(settings))
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as error:
        raise LLMError("Unexpected chat completion response") from error


def _anthropic(settings: AppSettings, prompt: str, model: str, system: str | None) -> str:
    key = settings.keys.anthropic_api_key
    if not key:
        raise LLMError("Anthropic API key is not configured")
    payload: dict = {"model": model, "max_tokens": 4000, "temperature": settings.language_model.temperature, "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    data = _post(f"{_base(settings, 'https://api.anthropic.com')}/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}, payload, _timeout(settings))
    return "".join(block.get("text", "") for block in data.get("content", []) if isinstance(block, dict))


def _gemini(settings: AppSettings, prompt: str, model: str, json_mode: bool, system: str | None) -> str:
    key = settings.keys.gemini_api_key
    if not key:
        raise LLMError("Gemini API key is not configured")
    payload: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": settings.language_model.temperature}}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    url = f"{_base(settings, 'https://generativelanguage.googleapis.com/v1beta')}/models/{model}:generateContent"
    data = _post(url, {"x-goog-api-key": key}, payload, _timeout(settings))
    try:
        return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError) as error:
        raise LLMError("Unexpected Gemini response") from error


def _ollama(settings: AppSettings, prompt: str, model: str, json_mode: bool, system: str | None) -> str:
    if not model:
        raise LLMError("No Ollama model selected. Use Settings → Ollama → Prepare best model.")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    payload: dict = {"model": model, "messages": messages, "stream": False, "keep_alive": "30m", "options": {"temperature": settings.language_model.temperature, "num_ctx": 16384}}
    if json_mode:
        payload["format"] = "json"
    data = _post(f"{_base(settings, OLLAMA_URL)}/api/chat", {}, payload, _timeout(settings))
    try:
        return str(data["message"]["content"])
    except (KeyError, TypeError) as error:
        raise LLMError("Unexpected Ollama response") from error


def model_for(settings: AppSettings) -> str:
    provider = settings.language_model.provider
    return settings.language_model.model or DEFAULT_MODELS.get(provider, "")


def complete(settings: AppSettings, prompt: str, *, json_mode: bool = True, system: str | None = None) -> str:
    """Send one prompt to the configured provider and return the text reply."""
    provider = settings.language_model.provider
    model = model_for(settings)
    if provider == "none":
        raise LLMError("No language model configured")
    if provider == "openai":
        if not settings.keys.openai_api_key:
            raise LLMError("OpenAI API key is not configured")
        return _openai_style(settings, prompt, _base(settings, "https://api.openai.com/v1"), settings.keys.openai_api_key, model, json_mode, system)
    if provider == "openai_compatible":
        if not settings.language_model.base_url:
            raise LLMError("Base URL is required for an OpenAI-compatible server")
        if not model:
            raise LLMError("Model name is required for an OpenAI-compatible server")
        return _openai_style(settings, prompt, _base(settings, ""), settings.keys.custom_llm_api_key, model, json_mode, system)
    if provider == "anthropic":
        return _anthropic(settings, prompt, model, system)
    if provider == "gemini":
        return _gemini(settings, prompt, model, json_mode, system)
    if provider == "ollama":
        return _ollama(settings, prompt, model, json_mode, system)
    raise LLMError(f"Unknown provider {provider}")


def is_configured(settings: AppSettings) -> bool:
    provider = settings.language_model.provider
    keys = settings.keys
    return {
        "none": False,
        "openai": bool(keys.openai_api_key),
        "anthropic": bool(keys.anthropic_api_key),
        "gemini": bool(keys.gemini_api_key),
        "ollama": bool(model_for(settings)),
        "openai_compatible": bool(settings.language_model.base_url and model_for(settings)),
    }.get(provider, False)


def test_connection(settings: AppSettings) -> dict:
    """Round-trip a tiny prompt and report latency; used by the Settings page."""
    import time

    start = time.time()
    reply = complete(settings, 'Reply with JSON {"ok": true}', json_mode=True)
    return {"ok": "true" in reply.lower(), "provider": settings.language_model.provider, "model": model_for(settings), "latency_ms": int((time.time() - start) * 1000), "reply": reply[:200]}
