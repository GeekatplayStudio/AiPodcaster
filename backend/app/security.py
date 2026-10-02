"""API-key protection for external access (scripts, MCP server, automations).

If no keys are configured the API stays open for local use. When at least one
key exists, requests must carry ``X-API-Key: <key>`` or ``Authorization: Bearer
<key>``; the browser UI is exempt unless ``api.require_for_ui`` is enabled,
identified by the configured CORS origins.
"""
from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import ALLOWED_ORIGINS, settings_store

PUBLIC_PATHS = {"/healthz", "/docs", "/openapi.json", "/redoc"}


def generate_key() -> str:
    return "apk_" + secrets.token_urlsafe(32)


def _presented(request: Request) -> str:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _valid(presented: str, keys: list[str]) -> bool:
    return any(hmac.compare_digest(presented, key) for key in keys)


def _from_ui(request: Request) -> bool:
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    return any(origin.startswith(allowed) for allowed in ALLOWED_ORIGINS)


async def api_key_middleware(request: Request, call_next):  # noqa: ANN001
    settings = settings_store.get()
    keys = settings.api.keys
    if not keys or request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    presented = _presented(request)
    if presented and _valid(presented, keys):
        return await call_next(request)
    if not presented and not settings.api.require_for_ui and _from_ui(request):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})
