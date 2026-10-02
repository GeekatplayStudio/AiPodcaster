from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings, settings_store
from app.main import app
from app.providers import llm, ollama, voice

client = TestClient(app)


class FakeResponse:
    def __init__(self, status_code: int, payload=None, content: bytes = b"", content_type: str = "application/json"):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}
        self.text = str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def settings_with(provider: str, model: str = "", base_url: str = "", **keys) -> AppSettings:
    settings = AppSettings()
    settings.language_model.provider, settings.language_model.model, settings.language_model.base_url = provider, model, base_url
    for name, value in keys.items():
        setattr(settings.keys, name, value)
    return settings


@pytest.mark.parametrize(
    ("provider", "model", "keys", "url_part", "payload"),
    [
        ("openai", "gpt-4o-mini", {"openai_api_key": "k"}, "api.openai.com/v1/chat/completions", {"choices": [{"message": {"content": '{"ok": true}'}}]}),
        ("anthropic", "", {"anthropic_api_key": "k"}, "api.anthropic.com/v1/messages", {"content": [{"type": "text", "text": '{"ok": true}'}]}),
        ("gemini", "gemini-2.5-flash", {"gemini_api_key": "k"}, "models/gemini-2.5-flash:generateContent", {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}),
        ("ollama", "gemma3:12b", {}, "/api/chat", {"message": {"content": '{"ok": true}'}}),
    ],
)
def test_complete_dispatches_to_each_provider(monkeypatch, provider, model, keys, url_part, payload):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"], seen["headers"], seen["json"] = url, headers, json
        return FakeResponse(200, payload)

    monkeypatch.setattr(httpx, "post", fake_post)
    settings = settings_with(provider, model, **keys)
    assert llm.complete(settings, "hi") == '{"ok": true}'
    assert url_part in seen["url"]
    if provider == "ollama":
        assert seen["json"]["format"] == "json" and seen["json"]["model"] == "gemma3:12b"
    if provider == "openai":
        assert seen["json"]["response_format"] == {"type": "json_object"} and seen["headers"]["Authorization"] == "Bearer k"
    if provider == "gemini":
        assert seen["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_openai_compatible_requires_base_url_and_model(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(200, {"choices": [{"message": {"content": "x"}}]}))
    with pytest.raises(llm.LLMError):
        llm.complete(settings_with("openai_compatible", "m"), "hi")
    assert llm.complete(settings_with("openai_compatible", "llama", "http://localhost:1234/v1"), "hi", json_mode=False) == "x"
    with pytest.raises(llm.LLMError):
        llm.complete(settings_with("openai"), "hi")  # no key
    assert not llm.is_configured(settings_with("ollama")) and llm.is_configured(settings_with("ollama", "gemma3:12b"))


def test_http_errors_become_llm_errors(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(500, {"error": "boom"}))
    with pytest.raises(llm.LLMError):
        llm.complete(settings_with("openai", openai_api_key="k"), "hi")


def test_ollama_recommendation_logic():
    m = ollama.ModelInfo
    assert ollama.recommend([], budget=22.0) == ("qwen3:32b", True, "No suitable local model yet; qwen3:32b fits in 22 GB")
    name, pull, _ = ollama.recommend([], budget=4.0)
    assert name == "gemma3:4b" and pull
    installed = [m("gemma3:12b", 7.6, "12.2B", "gemma3", 88), m("llama3:latest", 4.3, "8.0B", "llama3", 70)]
    name, pull, reason = ollama.recommend(installed, budget=11.0)
    assert name == "gemma3:12b" and not pull and "already installed" in reason
    name, pull, _ = ollama.recommend([m("llama3.2:3b", 2.0, "3.2B", "llama3.2", 60)], budget=22.0)
    assert name == "qwen3:32b" and pull
    assert ollama._score("qwen3:14b", "14B") == 90 and ollama._score("unknownmodel:7b", "7B") < 60


def test_ollama_status_when_down(monkeypatch):
    monkeypatch.setattr(ollama, "is_running", lambda url=None: False)
    result = client.get("/v1/providers/ollama/status").json()
    assert result["running"] is False and result["recommended"] == "" and "not running" in result["reason"]
    monkeypatch.setattr(ollama, "try_start_server", lambda url=None, wait_seconds=12: False)
    assert client.post("/v1/providers/ollama/setup", json={}).status_code == 503


def test_ollama_setup_selects_pulls_and_persists(monkeypatch):
    monkeypatch.setattr(ollama, "is_running", lambda url=None: True)
    monkeypatch.setattr(ollama, "list_models", lambda url=None: [ollama.ModelInfo("gemma3:12b", 7.6, "12.2B", "gemma3", 88)])
    monkeypatch.setattr(ollama, "budget_gb", lambda: 11.0)
    monkeypatch.setattr(ollama, "warm_up", lambda model, url=None: True)
    result = client.post("/v1/providers/ollama/setup", json={}).json()
    assert result["step"] == "ready" and result["model"] == "gemma3:12b"
    stored = settings_store.get()
    assert stored.language_model.provider == "ollama" and stored.language_model.model == "gemma3:12b"
    pulled = {}
    monkeypatch.setattr(ollama, "pull", lambda model, url=None: pulled.setdefault("model", model) is not None)
    result = client.post("/v1/providers/ollama/setup", json={"model": "qwen3:14b"}).json()
    assert result["step"] == "pulling" and pulled["model"] == "qwen3:14b"
    assert settings_store.get().language_model.model == "qwen3:14b"


def test_catalog_lists_all_backends():
    data = client.get("/v1/providers/catalog").json()
    assert {p["id"] for p in data["llm"]} == {"none", "ollama", "anthropic", "openai", "gemini", "openai_compatible"}
    assert {p["id"] for p in data["speech"]} == {"none", "openai", "elevenlabs", "descript", "custom_http"}
    assert any(p["supports_cloning"] for p in data["speech"])


def test_speech_registry_and_custom_template(monkeypatch, tmp_path):
    settings = AppSettings()
    settings.speech.provider = "custom_http"
    settings.speech.base_url = "http://tts.local/speak"
    settings.speech.voice = "anna"
    settings.keys.custom_tts_api_key = "secret"
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json)
        return FakeResponse(200, None, b"ID3audio", "audio/mpeg")

    monkeypatch.setattr(httpx, "post", fake_post)
    out = voice.build_speech_provider(settings).synthesize('Say "hi"', tmp_path / "a.mp3")
    assert out.read_bytes() == b"ID3audio"
    assert seen["json"] == {"text": 'Say "hi"', "voice": "anna"} and seen["headers"]["Authorization"] == "Bearer secret"
    settings.speech.provider = "descript"
    with pytest.raises(voice.SpeechError):
        voice.build_speech_provider(settings)  # no key
    settings.keys.descript_api_key = "d"
    settings.speech.voice = ""
    with pytest.raises(voice.SpeechError):
        voice.build_speech_provider(settings)  # no voice id
    settings.speech.voice = "ovd_123"
    assert voice.build_speech_provider(settings).name == "descript"


def test_api_keys_protect_external_access_but_not_ui():
    assert client.get("/v1/jobs").status_code == 200
    created = client.post("/v1/api-keys", json={"label": "mcp"}).json()
    key = created["key"]
    assert key.startswith("apk_") and client.get("/v1/api-keys", headers={"X-API-Key": key}).json()[0]["prefix"] == key[:8]
    try:
        assert client.get("/v1/jobs").status_code == 401
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/jobs", headers={"X-API-Key": key}).status_code == 200
        assert client.get("/v1/jobs", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert client.get("/v1/jobs", headers={"X-API-Key": "apk_wrong"}).status_code == 401
        assert client.get("/v1/jobs", headers={"Origin": "http://localhost:5173"}).status_code == 200
        masked = client.get("/v1/settings", headers={"X-API-Key": key}).json()
        assert masked["api"]["keys"] == [f"{key[:8]}…"]
        # PUT /v1/settings cannot inject keys
        masked["api"]["keys"] = ["apk_injected"]
        client.put("/v1/settings", json=masked, headers={"X-API-Key": key})
        assert settings_store.get().api.keys == [key]
    finally:
        assert client.delete(f"/v1/api-keys/{key[:8]}", headers={"X-API-Key": key}).status_code == 204
    assert client.get("/v1/jobs").status_code == 200


def test_mcp_server_registers_tools():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("aipodcaster_mcp", Path(__file__).resolve().parents[1] / "mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["aipodcaster_mcp"] = module
    spec.loader.exec_module(module)
    names = {tool.name for tool in module.server._tool_manager.list_tools()}
    assert {"upload_recording", "get_job", "approve_and_render", "run_fact_check", "list_libraries", "add_documents", "create_project", "ollama_setup", "test_language_model"} <= names
