"""Models for knowledge libraries, documents and projects."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl

from ..schemas import utc_now


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class Document(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    library_id: UUID
    name: str = Field(max_length=300)
    kind: str = Field(default="file", pattern="^(file|url)$")
    source_url: str | None = None
    content_type: str = ""
    size_bytes: int = 0
    status: DocumentStatus = DocumentStatus.QUEUED
    error: str | None = None
    chunk_count: int = 0
    characters: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Library(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    embedding: str = "local"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    documents: list[Document] = Field(default_factory=list)


class LibrarySummary(BaseModel):
    id: UUID
    name: str
    description: str
    embedding: str
    document_count: int
    ready_count: int
    chunk_count: int
    updated_at: datetime


class LibraryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)


class UrlIngest(BaseModel):
    url: HttpUrl
    name: str = Field(default="", max_length=300)


class Project(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    library_ids: list[UUID] = Field(default_factory=list, max_length=50)
    linked_project_ids: list[UUID] = Field(default_factory=list, max_length=50)
    online_fact_check: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1_000)
    library_ids: list[UUID] = Field(default_factory=list, max_length=50)
    linked_project_ids: list[UUID] = Field(default_factory=list, max_length=50)
    online_fact_check: bool = False


class SearchHit(BaseModel):
    library_id: UUID
    library_name: str
    document_id: UUID
    document_name: str
    source_url: str | None = None
    chunk_index: int
    text: str
    score: float
