"""Background indexing of library documents and URLs."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from ..config import AppSettings, settings_store
from . import index
from .parsing import ParseError, chunk_text, extract_text, html_to_text
from .schemas import Document, DocumentStatus
from .store import LibraryStore, library_store

log = logging.getLogger("aipodcaster.rag")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="index")
_active: set[UUID] = set()
_lock = threading.Lock()
MAX_URL_BYTES = 20 * 1024 * 1024


def index_document(library_id: UUID, document_id: UUID, store: LibraryStore = library_store, settings: AppSettings | None = None) -> Document:
    settings = settings or settings_store.get()
    library = store.get(library_id)
    document = next(d for d in library.documents if d.id == document_id)
    document.status = DocumentStatus.INDEXING
    document.error = None
    store.update_document(library_id, document)
    try:
        if document.kind == "url":
            text = _fetch_url(document.source_url or "")
        else:
            text = extract_text(store.document_path(library_id, document_id), document.name)
        chunks = chunk_text(text)
        count = index.index_document(library, document.id, document.name, document.source_url, chunks, settings)
        document.chunk_count, document.characters, document.status = count, len(text), DocumentStatus.READY
    except (ParseError, index.IndexError_, OSError, ValueError) as error:
        document.status, document.error = DocumentStatus.FAILED, str(error)[:500]
    except Exception as error:  # noqa: BLE001 - keep the worker alive
        log.exception("Indexing failed for %s", document_id)
        document.status, document.error = DocumentStatus.FAILED, str(error)[:500]
    return store.update_document(library_id, document)


def _fetch_url(url: str) -> str:
    import httpx

    if not url.startswith(("http://", "https://")):
        raise ParseError("Only http(s) URLs are supported")
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "AiPodcaster/1.0 (library import)"}) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_URL_BYTES:
                    raise ParseError("Remote document is too large")
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        tmp = Path(index.VECTORS_DIR).parent / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / f"url-{abs(hash(url))}.pdf"
        path.write_bytes(body)
        try:
            return extract_text(path, "remote.pdf")
        finally:
            path.unlink(missing_ok=True)
    text = body.decode(response.encoding or "utf-8", errors="replace")
    if "html" in content_type or "<html" in text[:2000].lower():
        text = html_to_text(text)
    if len(text.strip()) < 20:
        raise ParseError("No readable text at that URL")
    return text


def submit(library_id: UUID, document_id: UUID) -> bool:
    with _lock:
        if document_id in _active:
            return False
        _active.add(document_id)

    def task() -> None:
        try:
            index_document(library_id, document_id)
        finally:
            with _lock:
                _active.discard(document_id)

    _executor.submit(task)
    return True


def is_active(document_id: UUID) -> bool:
    with _lock:
        return document_id in _active
