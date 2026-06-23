from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.workspace_auth import WorkspaceAccess, require_workspace_access
from app.db.base import AsyncSessionLocal
from app.services.github_connection_service import (
    get_github_connection,
    get_github_connection_status,
    list_github_connections,
)
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


class GitHubConnectionRead(BaseModel):
    id: UUID
    provider: str
    status: str
    display_name: str | None = None
    external_account_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    token_expires_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    has_access_token: bool
    has_refresh_token: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GitHubConnectionListResponse(BaseModel):
    connections: list[GitHubConnectionRead]
    count: int
    provider: str
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubConnectionStatusResponse(BaseModel):
    provider: str
    status: str
    connection_id: UUID | None = None
    display_name: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    has_connection_record: bool
    has_valid_token_record: bool
    repository_read_available: bool
    repository_read_source: str
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


@router.get("/connections", response_model=GitHubConnectionListResponse)
async def list_github_connection_records(
    workspace_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubConnectionListResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        connections = await list_github_connections(
            session,
            workspace_id=workspace_id,
        )
    return GitHubConnectionListResponse(
        connections=[
            GitHubConnectionRead.model_validate(connection)
            for connection in connections
        ],
        count=len(connections),
        provider="github",
        is_live=False,
        warnings=[],
    )


@router.get("/connection-status", response_model=GitHubConnectionStatusResponse)
async def get_github_connection_state(
    workspace_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubConnectionStatusResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        payload = await get_github_connection_status(
            session,
            workspace_id=workspace_id,
        )
    return GitHubConnectionStatusResponse.model_validate(payload)


@router.get(
    "/connections/{connection_id}",
    response_model=GitHubConnectionRead,
)
async def get_github_connection_record(
    workspace_id: UUID,
    connection_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubConnectionRead:
    _ = access
    async with AsyncSessionLocal() as session:
        connection = await get_github_connection(
            session,
            workspace_id=workspace_id,
            connection_id=connection_id,
        )
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="github connection not found",
        )
    return GitHubConnectionRead.model_validate(connection)


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
