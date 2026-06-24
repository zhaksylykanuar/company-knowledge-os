from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN
from app.services.github_connection_service import (
    GITHUB_PROVIDER_TOKEN_WARNING,
    GitHubProviderTokenConnectionInput,
    create_or_update_github_provider_token_connection,
    get_github_connection,
    get_github_connection_status,
    list_github_connections,
)
from app.services.github_normalization_service import (
    GITHUB_NORMALIZATION_JOB_NOT_FOUND,
    GITHUB_NORMALIZATION_JOB_NOT_GITHUB,
    GITHUB_NORMALIZATION_JOB_NOT_MANUAL,
    GITHUB_NORMALIZATION_JOB_NOT_QUEUED,
    GITHUB_NORMALIZATION_PERSISTENCE_DEFERRED,
    GitHubNormalizationError,
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.github_operational_read_service import (
    list_workspace_github_operational_work,
)
from app.services.github_repository_read_service import (
    GitHubRepositoryFilters,
    list_workspace_github_repositories,
)
from app.services.github_sync_job_service import (
    GITHUB_SYNC_JOB_CONNECTION_NOT_CONNECTED,
    GITHUB_SYNC_JOB_CONNECTION_NOT_FOUND,
    GITHUB_SYNC_JOB_NO_EXECUTION_WARNING,
    GitHubManualSyncJobInput,
    GitHubSyncJobError,
    create_manual_github_sync_job,
    get_github_sync_job,
    list_github_sync_jobs,
)
from app.services.secret_encryption import SecretEncryptionError

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/github", tags=["github"])


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


class GitHubProviderTokenConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, max_length=255)
    external_account_id: str | None = Field(default=None, max_length=255)
    access_token: str = Field(min_length=1, max_length=4096)
    scopes: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_scope in value:
            scope = raw_scope.strip()
            if not scope:
                continue
            normalized.append(scope[:120])
        return normalized


class GitHubProviderTokenConnectionResponse(BaseModel):
    connection: GitHubConnectionRead
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubSyncJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sync_type: str = Field(default="manual", pattern="^manual$")
    cursor_before: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=1000)


class GitHubSyncJobRead(BaseModel):
    id: UUID
    workspace_id: UUID
    connection_id: UUID
    provider: str
    status: str
    sync_type: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cursor_before: dict[str, Any] | None = None
    cursor_after: dict[str, Any] | None = None
    records_seen: int
    records_created: int
    records_updated: int
    error_message: str | None = None
    logs: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubSyncJobCreateResponse(BaseModel):
    sync_job: GitHubSyncJobRead
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubSyncJobListResponse(BaseModel):
    sync_jobs: list[GitHubSyncJobRead]
    count: int
    provider: str
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubNormalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_repositories: bool = True
    include_issues: bool = True
    include_pull_requests: bool = True
    persist_if_supported: bool = False


class GitHubNormalizedRepositoryRead(BaseModel):
    entity_type: str
    provider: str
    external_id: str
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


class GitHubNormalizedIssueRead(BaseModel):
    entity_type: str
    provider: str
    external_id: str
    number: int | None = None
    title: str | None = None
    state: str | None = None
    source_url: str | None = None
    repository_full_name: str | None = None
    created_at_source: str | None = None
    updated_at_source: str | None = None
    evidence_refs: list[GitHubRepositoryEvidenceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubNormalizedPullRequestRead(BaseModel):
    entity_type: str
    provider: str
    external_id: str
    number: int | None = None
    title: str | None = None
    state: str | None = None
    source_url: str | None = None
    repository_full_name: str | None = None
    created_at_source: str | None = None
    updated_at_source: str | None = None
    merged_at_source: str | None = None
    evidence_refs: list[GitHubRepositoryEvidenceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubNormalizedPayloadRead(BaseModel):
    repositories: list[GitHubNormalizedRepositoryRead]
    issues: list[GitHubNormalizedIssueRead]
    pull_requests: list[GitHubNormalizedPullRequestRead]


class GitHubNormalizationCountsRead(BaseModel):
    repositories: int
    issues: int
    pull_requests: int


class GitHubNormalizationSyncJobRead(BaseModel):
    id: UUID
    status: str
    records_seen: int
    records_created: int
    records_updated: int
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GitHubNormalizationResponse(BaseModel):
    sync_job: GitHubNormalizationSyncJobRead
    normalized: GitHubNormalizedPayloadRead
    counts: GitHubNormalizationCountsRead
    is_live: bool
    provider_sync_started: bool
    local_normalization_performed: bool
    persistence_mode: str
    warnings: list[str] = Field(default_factory=list)


class GitHubOperationalIssueRead(BaseModel):
    id: UUID
    external_id: str | None = None
    number: int | None = None
    title: str
    state: str | None = None
    source_url: str | None = None
    repository_full_name: str | None = None
    repository_external_id: str | None = None
    source_record_id: UUID | None = None
    source_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubOperationalPullRequestRead(BaseModel):
    id: UUID
    external_id: str
    number: int
    title: str
    state: str
    source_url: str | None = None
    repository_id: UUID
    repository_full_name: str | None = None
    repository_external_id: str | None = None
    created_at_source: datetime | None = None
    updated_at_source: datetime | None = None
    merged_at_source: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubOperationalWorkCountsRead(BaseModel):
    issues: int
    pull_requests: int


class GitHubOperationalWorkResponse(BaseModel):
    issues: list[GitHubOperationalIssueRead]
    pull_requests: list[GitHubOperationalPullRequestRead]
    counts: GitHubOperationalWorkCountsRead
    state: str
    source: str
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


@router.post(
    "/connections/provider-token",
    response_model=GitHubProviderTokenConnectionResponse,
)
async def create_github_provider_token_connection(
    workspace_id: UUID,
    payload: GitHubProviderTokenConnectionRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubProviderTokenConnectionResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        try:
            connection = await create_or_update_github_provider_token_connection(
                session,
                workspace_id=workspace_id,
                payload=GitHubProviderTokenConnectionInput(
                    access_token=payload.access_token,
                    display_name=payload.display_name,
                    external_account_id=payload.external_account_id,
                    scopes=payload.scopes,
                    metadata=payload.metadata,
                ),
            )
            await session.commit()
        except SecretEncryptionError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="secret encryption is not configured",
            ) from exc
    return GitHubProviderTokenConnectionResponse(
        connection=GitHubConnectionRead.model_validate(connection),
        is_live=False,
        warnings=[GITHUB_PROVIDER_TOKEN_WARNING],
    )


@router.post(
    "/connections/{connection_id}/sync-jobs",
    response_model=GitHubSyncJobCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_github_manual_sync_job_record(
    workspace_id: UUID,
    connection_id: UUID,
    payload: GitHubSyncJobCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubSyncJobCreateResponse:
    async with AsyncSessionLocal() as session:
        try:
            sync_job = await create_manual_github_sync_job(
                session,
                workspace_id=workspace_id,
                connection_id=connection_id,
                payload=GitHubManualSyncJobInput(
                    cursor_before=payload.cursor_before,
                    notes=payload.notes,
                    requested_by=access.actor.auth_mode,
                ),
            )
            await session.commit()
        except GitHubSyncJobError as exc:
            await session.rollback()
            if exc.detail == GITHUB_SYNC_JOB_CONNECTION_NOT_FOUND:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=exc.detail,
                ) from exc
            if exc.detail == GITHUB_SYNC_JOB_CONNECTION_NOT_CONNECTED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=exc.detail,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubSyncJobCreateResponse(
        sync_job=GitHubSyncJobRead.model_validate(sync_job),
        is_live=False,
        execution_started=False,
        warnings=[GITHUB_SYNC_JOB_NO_EXECUTION_WARNING],
    )


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


@router.get("/sync-jobs", response_model=GitHubSyncJobListResponse)
async def list_github_sync_job_records(
    workspace_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubSyncJobListResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        sync_jobs = await list_github_sync_jobs(
            session,
            workspace_id=workspace_id,
        )
    return GitHubSyncJobListResponse(
        sync_jobs=[
            GitHubSyncJobRead.model_validate(sync_job)
            for sync_job in sync_jobs
        ],
        count=len(sync_jobs),
        provider="github",
        is_live=False,
        warnings=[],
    )


@router.post(
    "/sync-jobs/{sync_job_id}/normalize-local",
    response_model=GitHubNormalizationResponse,
)
async def normalize_github_sync_job_record_local(
    workspace_id: UUID,
    sync_job_id: UUID,
    payload: GitHubNormalizationRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubNormalizationResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        try:
            result = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=sync_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=payload.include_repositories,
                    include_issues=payload.include_issues,
                    include_pull_requests=payload.include_pull_requests,
                    persist_if_supported=payload.persist_if_supported,
                ),
            )
            await session.commit()
        except GitHubNormalizationError as exc:
            await session.rollback()
            if exc.detail == GITHUB_NORMALIZATION_JOB_NOT_FOUND:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=exc.detail,
                ) from exc
            if exc.detail == GITHUB_NORMALIZATION_JOB_NOT_QUEUED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=exc.detail,
                ) from exc
            if exc.detail in {
                GITHUB_NORMALIZATION_JOB_NOT_GITHUB,
                GITHUB_NORMALIZATION_JOB_NOT_MANUAL,
                GITHUB_NORMALIZATION_PERSISTENCE_DEFERRED,
            }:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=exc.detail,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubNormalizationResponse.model_validate(result)


@router.get("/operational-work", response_model=GitHubOperationalWorkResponse)
async def list_github_operational_work(
    workspace_id: UUID,
    state: str = Query(default="open", pattern="^(open|closed|merged|all)$"),
    limit: int = Query(default=100, ge=1, le=200),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubOperationalWorkResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        result = await list_workspace_github_operational_work(
            session=session,
            workspace_id=workspace_id,
            state=state,
            limit=limit,
        )
    return GitHubOperationalWorkResponse.model_validate(result)


@router.get("/sync-jobs/{sync_job_id}", response_model=GitHubSyncJobRead)
async def get_github_sync_job_record(
    workspace_id: UUID,
    sync_job_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> GitHubSyncJobRead:
    _ = access
    async with AsyncSessionLocal() as session:
        sync_job = await get_github_sync_job(
            session,
            workspace_id=workspace_id,
            sync_job_id=sync_job_id,
        )
    if sync_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="github sync job not found",
        )
    return GitHubSyncJobRead.model_validate(sync_job)


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
