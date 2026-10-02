"""Vector index on top of ChromaDB with pluggable embedding providers.

One Chroma collection per library. The embedding provider is fixed when a
library is created so queries always use the same model as the stored vectors.
"""
from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from uuid import UUID

from ..config import DATA_DIR, AppSettings
from .schemas import Library, SearchHit

VECTORS_DIR = DATA_DIR / "vectors"
_client_lock = threading.Lock()
_client = None
_embedders: dict[str, object] = {}


class IndexError_(RuntimeError):
    pass


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            import chromadb
            from chromadb.config import Settings

            VECTORS_DIR.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(VECTORS_DIR), settings=Settings(anonymized_telemetry=False, allow_reset=True))
        return _client


class OpenAIEmbedding:
    """Minimal Chroma-compatible embedding function using the OpenAI REST API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise IndexError_("OpenAI API key is required for OpenAI embeddings")
        self._api_key, self._model = api_key, model or "text-embedding-3-small"

    def name(self) -> str:
        return "openai"

    def __call__(self, input: Sequence[str]):  # noqa: A002 - Chroma protocol
        import httpx

        vectors = []
        for start in range(0, len(input), 100):
            batch = list(input[start : start + 100])
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": batch},
                timeout=120,
            )
            if response.status_code >= 400:
                raise IndexError_(f"OpenAI embeddings failed ({response.status_code})")
            vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors

    def embed_query(self, input: Sequence[str]):  # noqa: A002
        return self(input)

    def embed_documents(self, input: Sequence[str]):  # noqa: A002
        return self(input)


def embedding_function(kind: str, settings: AppSettings):
    key = f"{kind}:{settings.fact_check.embedding_model}" if kind == "openai" else "local"
    if key in _embedders:
        return _embedders[key]
    if kind == "openai":
        function = OpenAIEmbedding(settings.keys.openai_api_key, settings.fact_check.embedding_model)
    else:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        function = DefaultEmbeddingFunction()
    _embedders[key] = function
    return function


def embed_texts(kind: str, settings: AppSettings, texts: list[str]) -> list[list[float]]:
    function = embedding_function(kind, settings)
    return [list(map(float, vector)) for vector in function(texts)]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _collection_name(library_id: UUID) -> str:
    return f"lib_{library_id.hex}"


def _collection(library: Library, settings: AppSettings):
    client = _get_client()
    return client.get_or_create_collection(name=_collection_name(library.id), embedding_function=embedding_function(library.embedding, settings), metadata={"hnsw:space": "cosine"})


def index_document(library: Library, document_id: UUID, document_name: str, source_url: str | None, chunks: list[str], settings: AppSettings) -> int:
    collection = _collection(library, settings)
    delete_document(library, document_id, settings)
    if not chunks:
        return 0
    ids = [f"{document_id}:{index}" for index in range(len(chunks))]
    metadatas = [{"document_id": str(document_id), "document_name": document_name, "chunk_index": index, "source_url": source_url or ""} for index in range(len(chunks))]
    for start in range(0, len(chunks), 64):
        collection.add(ids=ids[start : start + 64], documents=chunks[start : start + 64], metadatas=metadatas[start : start + 64])
    return len(chunks)


def delete_document(library: Library, document_id: UUID, settings: AppSettings) -> None:
    collection = _collection(library, settings)
    try:
        collection.delete(where={"document_id": str(document_id)})
    except Exception:  # noqa: BLE001 - nothing to delete
        pass


def delete_library(library_id: UUID) -> None:
    try:
        _get_client().delete_collection(_collection_name(library_id))
    except Exception:  # noqa: BLE001 - collection may not exist
        pass


def search(libraries: list[Library], query: str, settings: AppSettings, limit: int = 5) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for library in libraries:
        collection = _collection(library, settings)
        if collection.count() == 0:
            continue
        result = collection.query(query_texts=[query], n_results=min(limit, collection.count()), include=["documents", "metadatas", "distances"])
        for text, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0], strict=False):
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            hits.append(
                SearchHit(
                    library_id=library.id,
                    library_name=library.name,
                    document_id=UUID(str(metadata["document_id"])),
                    document_name=str(metadata["document_name"]),
                    source_url=str(metadata.get("source_url") or "") or None,
                    chunk_index=int(metadata["chunk_index"]),
                    text=text,
                    score=score,
                )
            )
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def reset_for_tests() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.reset()
            except Exception:  # noqa: BLE001
                pass
        _client = None
