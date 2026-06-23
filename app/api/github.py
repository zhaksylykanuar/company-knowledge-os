from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.github_repository_read_service import (
    GitHubRepositoryFilters,
    list_workspace_github_repositories,
)

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/github", tags=["github"])


class GitHubRepositoryEvidenceRef(BaseModel):
    kind: str
    source: str
    ref: str
    url: str | None = None


class GitHubRepositoryRead(BaseModel):
    id: str
    name: str
    full_name: str
    default_branch: str | None = None
    visibility: str
    archived: bool
    source_url: str | None = None
    last_activity_at: str | None = None
    source: str
    evidence_refs: list[GitHubRepositoryEvidenceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubRepositoryListResponse(BaseModel):
    repositories: list[GitHubRepositoryRead]
    count: int
    source: str
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


@router.get("/repositories", response_model=GitHubRepositoryListResponse)
async def list_github_repositories(
    workspace_id: UUID,
    search: str | None = Query(default=None, max_length=200),
    visibility: str | None = Query(
        default=None,
        pattern="^(public|private|internal|unknown)$",
    ),
    archived: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubRepositoryListResponse:
    _ = access
    filters = GitHubRepositoryFilters(
        search=search,
        visibility=visibility,
        archived=archived,
        limit=limit,
    )
    async with AsyncSessionLocal() as session:
        result = await list_workspace_github_repositories(
            session=session,
            workspace_id=workspace_id,
            filters=filters,
        )
    return GitHubRepositoryListResponse(
        repositories=[
            GitHubRepositoryRead.model_validate(repository)
            for repository in result.repositories
        ],
        count=result.count,
        source=result.source,
        is_live=result.is_live,
        warnings=result.warnings,
    )
