"""Projects group episodes and decide which libraries are used for fact checking."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from ..rag.schemas import Project, ProjectUpsert
from ..rag.store import library_store, project_store

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _validate_links(body: ProjectUpsert, own_id: UUID | None) -> None:
    for library_id in body.library_ids:
        library_store.get(library_id)
    for project_id in body.linked_project_ids:
        if project_id == own_id:
            raise HTTPException(status_code=422, detail="A project cannot link to itself")
        project_store.get(project_id)


@router.get("", response_model=list[Project])
async def list_projects() -> list[Project]:
    return project_store.list()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectUpsert) -> Project:
    _validate_links(body, None)
    return project_store.save(Project(**body.model_dump()))


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: UUID) -> Project:
    return project_store.get(project_id)


@router.put("/{project_id}", response_model=Project)
async def update_project(project_id: UUID, body: ProjectUpsert) -> Project:
    project = project_store.get(project_id)
    _validate_links(body, project_id)
    updated = project.model_copy(update=body.model_dump())
    return project_store.save(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID) -> None:
    project_store.delete(project_id)


@router.get("/{project_id}/libraries", response_model=list[UUID])
async def effective_libraries(project_id: UUID) -> list[UUID]:
    """All library IDs the project can use, including those inherited from linked projects."""
    return project_store.resolve_library_ids(project_store.get(project_id))
