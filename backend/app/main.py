"""AiPodcaster API.

Review-first podcast post-production: upload → transcribe → propose cleanup
edits → human approval → render → publish kit.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import ALLOWED_ORIGINS, DATA_DIR, PUBLIC_URL, settings_store
from .routers import episodes, jobs, libraries, projects, providers, publishing, settings
from .security import api_key_middleware
from .services import estimates, languages, workflow
from .storage import JOBS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        resumed = workflow.resume_incomplete()
        if resumed:
            logging.getLogger("aipodcaster").info("Resumed %d interrupted job(s)", len(resumed))
    except Exception:  # noqa: BLE001 - never block startup
        logging.getLogger("aipodcaster").exception("Could not resume interrupted jobs")
    yield


app = FastAPI(
    title="AiPodcaster API",
    version="1.0.0",
    description="Review-first podcast post-production by Geekatplay Studio.",
    contact={"name": "Geekatplay Studio, Vladimir Chopine", "url": "https://www.geekatplay.com"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(settings.router)
app.include_router(libraries.router)
app.include_router(projects.router)
app.include_router(providers.router)
app.include_router(providers.keys_router)
app.include_router(publishing.router)


app.middleware("http")(api_key_middleware)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(_: Request, error: Exception) -> JSONResponse:
    logging.getLogger("aipodcaster").exception("Unhandled error: %s", error)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/v1/info")
async def info() -> dict:
    """Public facts the client needs: where the API lives, supported languages, time estimates."""
    return {
        "name": "AiPodcaster",
        "version": app.version,
        "public_url": PUBLIC_URL,
        "docs_url": f"{PUBLIC_URL}/docs",
        "languages": languages.LANGUAGE_NAMES,
        "estimates": estimates.describe(settings_store.get()),
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
