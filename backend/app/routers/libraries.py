"""Knowledge library endpoints: create libraries, upload/index documents, search."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, status

from ..config import settings_store
from ..rag import index, ingest
from ..rag.parsing import ALLOWED_DOCUMENT_EXTENSIONS, MAX_DOCUMENT_BYTES
from ..rag.schemas import Document, Library, LibraryCreate, LibrarySummary, SearchHit, UrlIngest
from ..rag.store import library_store
from ..storage import SAFE_NAME

router = APIRouter(prefix="/v1/libraries", tags=["libraries"])
CHUNK = 1024 * 1024


def safe_document_name(name: str) -> str:
    candidate = Path(name.replace("\\", "/")).name.strip()
    cleaned = SAFE_NAME.sub("_", candidate).strip(" .")
    if not cleaned or len(cleaned) > 200:
        raise HTTPException(status_code=422, detail="Invalid document name")
    if Path(cleaned).suffix.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported document type; allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}")
    return cleaned


@router.get("", response_model=list[LibrarySummary])
async def list_libraries() -> list[LibrarySummary]:
    return library_store.list()


@router.post("", response_model=Library, status_code=status.HTTP_201_CREATED)
async def create_library(body: LibraryCreate) -> Library:
    embedding = settings_store.get().fact_check.embedding_provider
    return library_store.create(Library(name=body.name.strip(), description=body.description.strip(), embedding=embedding))


@router.get("/{library_id}", response_model=Library)
async def get_library(library_id: UUID) -> Library:
    return library_store.get(library_id)


@router.put("/{library_id}", response_model=Library)
async def update_library(library_id: UUID, body: LibraryCreate) -> Library:
    library = library_store.get(library_id)
    library.name, library.description = body.name.strip(), body.description.strip()
    return library_store.save(library)


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library(library_id: UUID) -> None:
    library = library_store.get(library_id)
    if any(ingest.is_active(d.id) for d in library.documents):
        raise HTTPException(status_code=409, detail="Documents are still indexing")
    index.delete_library(library_id)
    library_store.delete(library_id)


@router.post("/{library_id}/documents", response_model=list[Document], status_code=status.HTTP_201_CREATED)
async def upload_documents(library_id: UUID, files: list[UploadFile]) -> list[Document]:
    """Upload one or many documents; each is indexed in the background."""
    library = library_store.get(library_id)
    if not files:
        raise HTTPException(status_code=422, detail="No files provided")
    created: list[Document] = []
    for file in files:
        name = safe_document_name(file.filename or "")
        document = Document(library_id=library.id, name=name, content_type=file.content_type or "")
        target = library_store.document_path(library.id, document.id)
        written = 0
        try:
            with target.open("wb") as handle:
                while chunk := await file.read(CHUNK):
                    written += len(chunk)
                    if written > MAX_DOCUMENT_BYTES:
                        raise HTTPException(status_code=413, detail=f"{name} exceeds the document size limit")
                    handle.write(chunk)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        if written == 0:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f"{name} is empty")
        document.size_bytes = written
        created.append(document)
    library.documents.extend(created)
    library_store.save(library)
    for document in created:
        ingest.submit(library.id, document.id)
    return created


@router.post("/{library_id}/documents/url", response_model=Document, status_code=status.HTTP_201_CREATED)
async def add_url(library_id: UUID, body: UrlIngest) -> Document:
    library = library_store.get(library_id)
    url = str(body.url)
    document = Document(library_id=library.id, name=(body.name.strip() or url)[:300], kind="url", source_url=url)
    library.documents.append(document)
    library_store.save(library)
    ingest.submit(library.id, document.id)
    return document


@router.post("/{library_id}/documents/{document_id}/reindex", response_model=Document)
async def reindex(library_id: UUID, document_id: UUID) -> Document:
    document = _find(library_id, document_id)
    if not ingest.submit(library_id, document_id):
        raise HTTPException(status_code=409, detail="Document is already indexing")
    return document


@router.delete("/{library_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(library_id: UUID, document_id: UUID) -> None:
    library = library_store.get(library_id)
    _find(library_id, document_id)
    if ingest.is_active(document_id):
        raise HTTPException(status_code=409, detail="Document is still indexing")
    index.delete_document(library, document_id, settings_store.get())
    library_store.document_path(library_id, document_id).unlink(missing_ok=True)
    library.documents = [d for d in library.documents if d.id != document_id]
    library_store.save(library)


@router.get("/{library_id}/search", response_model=list[SearchHit])
async def search_library(library_id: UUID, q: str, limit: int = 5) -> list[SearchHit]:
    query = q.strip()
    if not 2 <= len(query) <= 500:
        raise HTTPException(status_code=422, detail="Query must be 2-500 characters")
    return index.search([library_store.get(library_id)], query, settings_store.get(), limit=max(1, min(limit, 20)))


def _find(library_id: UUID, document_id: UUID) -> Document:
    library = library_store.get(library_id)
    document = next((d for d in library.documents if d.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
