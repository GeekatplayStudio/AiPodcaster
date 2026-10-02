"""JSON persistence for libraries, documents and projects (UUID-keyed paths only)."""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from ..config import DATA_DIR
from ..schemas import utc_now
from .schemas import Document, DocumentStatus, Library, LibrarySummary, Project

LIBRARIES_DIR = DATA_DIR / "libraries"
PROJECTS_DIR = DATA_DIR / "projects"


class LibraryStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.RLock()

    def library_dir(self, library_id: UUID) -> Path:
        path = (self._root / str(library_id)).resolve()
        if path.parent != self._root.resolve():
            raise HTTPException(status_code=400, detail="Invalid library path")
        return path

    def document_path(self, library_id: UUID, document_id: UUID) -> Path:
        return self.library_dir(library_id) / "files" / f"{document_id}.bin"

    def create(self, library: Library) -> Library:
        with self._lock:
            directory = self.library_dir(library.id)
            (directory / "files").mkdir(parents=True, exist_ok=False)
            self._write(library)
            return library

    def get(self, library_id: UUID) -> Library:
        path = self.library_dir(library_id) / "library.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Library not found")
        return Library.model_validate_json(path.read_text("utf-8"))

    def save(self, library: Library) -> Library:
        with self._lock:
            library.updated_at = utc_now()
            self._write(library)
            return library

    def update_document(self, library_id: UUID, document: Document) -> Document:
        """Replace one document record atomically (used by the indexing worker)."""
        with self._lock:
            library = self.get(library_id)
            document.updated_at = utc_now()
            library.documents = [document if d.id == document.id else d for d in library.documents]
            self.save(library)
            return document

    def list(self) -> list[LibrarySummary]:
        items: list[LibrarySummary] = []
        if not self._root.exists():
            return items
        for child in self._root.iterdir():
            try:
                library = self.get(UUID(child.name))
            except (ValueError, HTTPException):
                continue
            items.append(summarise(library))
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def delete(self, library_id: UUID) -> None:
        with self._lock:
            directory = self.library_dir(library_id)
            if not directory.exists():
                raise HTTPException(status_code=404, detail="Library not found")
            shutil.rmtree(directory, ignore_errors=True)

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)

    def _write(self, library: Library) -> None:
        path = self.library_dir(library.id) / "library.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(library.model_dump(mode="json"), indent=2), "utf-8")
        tmp.replace(path)


def summarise(library: Library) -> LibrarySummary:
    return LibrarySummary(
        id=library.id,
        name=library.name,
        description=library.description,
        embedding=library.embedding,
        document_count=len(library.documents),
        ready_count=sum(1 for d in library.documents if d.status == DocumentStatus.READY),
        chunk_count=sum(d.chunk_count for d in library.documents),
        updated_at=library.updated_at,
    )


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.RLock()

    def _path(self, project_id: UUID) -> Path:
        path = (self._root / f"{project_id}.json").resolve()
        if path.parent != self._root.resolve():
            raise HTTPException(status_code=400, detail="Invalid project path")
        return path

    def save(self, project: Project) -> Project:
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            project.updated_at = utc_now()
            tmp = self._path(project.id).with_suffix(".tmp")
            tmp.write_text(json.dumps(project.model_dump(mode="json"), indent=2), "utf-8")
            tmp.replace(self._path(project.id))
            return project

    def get(self, project_id: UUID) -> Project:
        path = self._path(project_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Project not found")
        return Project.model_validate_json(path.read_text("utf-8"))

    def list(self) -> list[Project]:
        if not self._root.exists():
            return []
        projects: list[Project] = []
        for child in self._root.glob("*.json"):
            try:
                projects.append(Project.model_validate_json(child.read_text("utf-8")))
            except ValueError:
                continue
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def delete(self, project_id: UUID) -> None:
        path = self._path(project_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Project not found")
        path.unlink()

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)

    def resolve_library_ids(self, project: Project, depth: int = 2) -> list[UUID]:
        """Libraries of this project plus those of linked projects (one hop deep by default)."""
        seen: list[UUID] = []
        visited: set[UUID] = set()

        def walk(current: Project, remaining: int) -> None:
            visited.add(current.id)
            for library_id in current.library_ids:
                if library_id not in seen:
                    seen.append(library_id)
            if remaining <= 0:
                return
            for linked in current.linked_project_ids:
                if linked in visited:
                    continue
                try:
                    walk(self.get(linked), remaining - 1)
                except HTTPException:
                    continue

        walk(project, depth)
        return seen


library_store = LibraryStore(LIBRARIES_DIR)
project_store = ProjectStore(PROJECTS_DIR)
