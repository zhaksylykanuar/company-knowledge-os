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
from app.db.integration_models import INTEGRATION_CONNECTION_STATUS_CONNECTED
from app.services.github_connection_service import (
    GITHUB_APP_INSTALLATION_ALREADY_BOUND,
    GITHUB_PROVIDER_TOKEN_WARNING,
    GitHubAppInstallationConnectionError,
    GitHubAppInstallationConnectionInput,
    GitHubProviderTokenConnectionInput,
    create_or_update_github_app_installation_connection,
    create_or_update_github_provider_token_connection,
    get_github_connection,
    get_github_connection_status,
    list_github_connections,
)
from app.services.github_app_live_sync_service import (
    GitHubAppLiveSyncConflictError,
    GitHubAppLiveSyncError,
    GitHubAppLiveSyncInput,
    GitHubAppLiveSyncNotFoundError,
    GitHubAppLiveSyncProviderReadError,
    sync_github_app_installation_repositories,
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
from app.services.github_selected_issue_sync_service import (
    GitHubSelectedIssueSyncConflictError,
    GitHubSelectedIssueSyncError,
    GitHubSelectedIssueSyncInput,
    GitHubSelectedIssueSyncNotFoundError,
    GitHubSelectedIssueSyncProviderReadError,
    sync_selected_repository_issues,
)
from app.services.github_selected_pr_sync_service import (
    GitHubSelectedPRSyncConflictError,
    GitHubSelectedPRSyncError,
    GitHubSelectedPRSyncInput,
    GitHubSelectedPRSyncNotFoundError,
    GitHubSelectedPRSyncProviderReadError,
    sync_selected_repository_pull_requests,
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
    connection_method: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class GitHubConnectionListResponse(BaseModel):
    connections: list[GitHubConnectionRead]
    count: int
    provider: str
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubAppConfigStatusRead(BaseModel):
    configured: bool
    app_id_configured: bool
    app_slug: str | None = None
    private_key_configured: bool
    private_key_source: str | None = None
    webhook_secret_configured: bool
    setup_url: str | None = None
    callback_url: str | None = None
    missing_env: list[str] = Field(default_factory=list)
    installation_tokens_persisted: bool
    provider_writes_enabled: bool


class GitHubConnectionStatusResponse(BaseModel):
    provider: str
    status: str
    connection_method: str | None = None
    connection_id: UUID | None = None
    display_name: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    has_connection_record: bool
    has_valid_token_record: bool
    repository_read_available: bool
    repository_read_source: str
    is_live: bool
    app: GitHubAppConfigStatusRead
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


class GitHubAppSelectedRepositoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str | int | None = Field(default=None)
    name: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    private: bool | None = None


class GitHubAppInstallationConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    installation_id: str = Field(min_length=1, max_length=64)
    account_login: str = Field(min_length=1, max_length=255)
    account_id: str | None = Field(default=None, max_length=64)
    repository_selection: str = Field(default="unknown", max_length=32)
    selected_repositories: list[GitHubAppSelectedRepositoryRequest] = Field(
        default_factory=list,
        max_length=100,
    )
    display_name: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GitHubAppInstallationConnectionResponse(BaseModel):
    connection: GitHubConnectionRead
    is_live: bool
    provider_sync_started: bool
    installation_access_token_persisted: bool
    external_write_performed: bool
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


class GitHubAppLiveSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    repositories: list[str] = Field(min_length=1, max_length=20)
    include_issues: bool = True
    include_pull_requests: bool = True
    issue_states: list[str] = Field(
        default_factory=lambda: ["open", "closed"],
        max_length=3,
    )
    pull_request_states: list[str] = Field(
        default_factory=lambda: ["open", "closed", "merged"],
        max_length=4,
    )


class GitHubAppLiveSyncRepositoryRead(BaseModel):
    full_name: str
    synced_issues: int
    synced_pull_requests: int
    skipped_pull_requests: int


class GitHubAppLiveSyncTotalsRead(BaseModel):
    repositories: int
    issues: int
    pull_requests: int
    skipped_pull_requests: int


class GitHubAppLiveSyncCapabilitiesRead(BaseModel):
    read_only_sync: bool
    external_writes: bool
    installation_access_token_persisted: bool


class GitHubAppLiveSyncResponse(BaseModel):
    workspace_id: UUID
    connection_id: UUID
    installation_id: str
    repositories: list[GitHubAppLiveSyncRepositoryRead]
    totals: GitHubAppLiveSyncTotalsRead
    sync_job: GitHubNormalizationSyncJobRead
    counts: GitHubNormalizationCountsRead
    capabilities: GitHubAppLiveSyncCapabilitiesRead
    is_live: bool
    provider_sync_started: bool
    local_normalization_performed: bool
    external_write_performed: bool
    persistence_mode: str
    warnings: list[str] = Field(default_factory=list)


class GitHubLocalSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_repositories: bool = True
    include_issues: bool = True
    include_pull_requests: bool = True


class GitHubLocalSyncResponse(BaseModel):
    sync_job: GitHubNormalizationSyncJobRead
    counts: GitHubNormalizationCountsRead
    status: str
    message: str
    capability_mode: str
    is_live: bool
    provider_sync_started: bool
    local_normalization_performed: bool
    persistence_mode: str
    warnings: list[str] = Field(default_factory=list)


class GitHubSelectedIssueSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    repositories: list[str] = Field(min_length=1, max_length=20)
    states: list[str] = Field(default_factory=lambda: ["open", "closed"], max_length=3)


class GitHubSelectedIssueSyncRepositoryRead(BaseModel):
    full_name: str
    synced_issues: int
    open_issues: int
    closed_issues: int
    skipped_pull_requests: int


class GitHubSelectedIssueSyncTotalsRead(BaseModel):
    repositories: int
    issues: int
    open_issues: int
    closed_issues: int
    skipped_pull_requests: int


class GitHubSelectedIssueSyncCapabilitiesRead(BaseModel):
    read_only_sync: bool
    external_writes: bool


class GitHubSelectedIssueSyncResponse(BaseModel):
    workspace_id: UUID
    repositories: list[GitHubSelectedIssueSyncRepositoryRead]
    totals: GitHubSelectedIssueSyncTotalsRead
    sync_job: GitHubNormalizationSyncJobRead
    counts: GitHubNormalizationCountsRead
    capabilities: GitHubSelectedIssueSyncCapabilitiesRead
    is_live: bool
    provider_sync_started: bool
    external_write_performed: bool
    warnings: list[str] = Field(default_factory=list)


class GitHubSelectedPullRequestSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    repositories: list[str] = Field(min_length=1, max_length=20)
    states: list[str] = Field(
        default_factory=lambda: ["open", "closed", "merged"],
        max_length=4,
    )


class GitHubSelectedPullRequestSyncRepositoryRead(BaseModel):
    full_name: str
    synced_pull_requests: int
    open_pull_requests: int
    closed_pull_requests: int
    merged_pull_requests: int


class GitHubSelectedPullRequestSyncTotalsRead(BaseModel):
    repositories: int
    pull_requests: int
    open_pull_requests: int
    closed_pull_requests: int
    merged_pull_requests: int


class GitHubSelectedPullRequestSyncCapabilitiesRead(BaseModel):
    read_only_sync: bool
    external_writes: bool


class GitHubSelectedPullRequestSyncResponse(BaseModel):
    workspace_id: UUID
    repositories: list[GitHubSelectedPullRequestSyncRepositoryRead]
    totals: GitHubSelectedPullRequestSyncTotalsRead
    sync_job: GitHubNormalizationSyncJobRead
    counts: GitHubNormalizationCountsRead
    capabilities: GitHubSelectedPullRequestSyncCapabilitiesRead
    is_live: bool
    provider_sync_started: bool
    external_write_performed: bool
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
    "/connections/app-installation",
    response_model=GitHubAppInstallationConnectionResponse,
)
async def create_github_app_installation_connection(
    workspace_id: UUID,
    payload: GitHubAppInstallationConnectionRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubAppInstallationConnectionResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        try:
            connection = await create_or_update_github_app_installation_connection(
                session,
                workspace_id=workspace_id,
                payload=GitHubAppInstallationConnectionInput(
                    installation_id=payload.installation_id,
                    account_login=payload.account_login,
                    account_id=payload.account_id,
                    repository_selection=payload.repository_selection,
                    selected_repositories=[
                        repository.model_dump(exclude_none=True)
                        for repository in payload.selected_repositories
                    ],
                    display_name=payload.display_name,
                    metadata=payload.metadata,
                ),
            )
            await session.commit()
        except GitHubAppInstallationConnectionError as exc:
            await session.rollback()
            if exc.detail == GITHUB_APP_INSTALLATION_ALREADY_BOUND:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=exc.detail,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubAppInstallationConnectionResponse(
        connection=GitHubConnectionRead.model_validate(connection),
        is_live=False,
        provider_sync_started=False,
        installation_access_token_persisted=False,
        external_write_performed=False,
        warnings=[
            "GitHub App installation connection recorded; live provider sync is not started by this endpoint."
        ],
    )


@router.post(
    "/connections/app-installation/sync",
    response_model=GitHubAppLiveSyncResponse,
)
async def run_github_app_installation_live_sync(
    workspace_id: UUID,
    payload: GitHubAppLiveSyncRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubAppLiveSyncResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_github_app_installation_repositories(
                session,
                workspace_id=workspace_id,
                input_payload=GitHubAppLiveSyncInput(
                    connection_id=payload.connection_id,
                    repositories=payload.repositories,
                    include_issues=payload.include_issues,
                    include_pull_requests=payload.include_pull_requests,
                    issue_states=payload.issue_states,
                    pull_request_states=payload.pull_request_states,
                ),
                requested_by=access.actor.auth_mode,
            )
            await session.commit()
        except GitHubAppLiveSyncNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except GitHubAppLiveSyncConflictError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
        except GitHubAppLiveSyncProviderReadError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=exc.detail,
            ) from exc
        except GitHubAppLiveSyncError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubAppLiveSyncResponse.model_validate(result)


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


@router.post("/local-sync", response_model=GitHubLocalSyncResponse)
async def run_github_local_sync(
    workspace_id: UUID,
    payload: GitHubLocalSyncRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubLocalSyncResponse:
    async with AsyncSessionLocal() as session:
        try:
            connections = await list_github_connections(
                session,
                workspace_id=workspace_id,
            )
            connection = next(
                (
                    candidate
                    for candidate in connections
                    if candidate["status"] == INTEGRATION_CONNECTION_STATUS_CONNECTED
                ),
                None,
            )
            if connection is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="github connected connection record required for local sync",
                )

            sync_job = await create_manual_github_sync_job(
                session,
                workspace_id=workspace_id,
                connection_id=connection["id"],
                payload=GitHubManualSyncJobInput(
                    cursor_before=None,
                    notes="product local GitHub sync control",
                    requested_by=access.actor.auth_mode,
                ),
            )
            result = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=sync_job["id"],
                options=GitHubNormalizationOptions(
                    include_repositories=payload.include_repositories,
                    include_issues=payload.include_issues,
                    include_pull_requests=payload.include_pull_requests,
                    persist_if_supported=True,
                ),
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
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

    counts = GitHubNormalizationCountsRead.model_validate(result["counts"])
    records_count = counts.repositories + counts.issues + counts.pull_requests
    message = (
        "Local GitHub data normalized into canonical backend state."
        if records_count > 0
        else "No supported local GitHub data was available to normalize."
    )
    return GitHubLocalSyncResponse(
        sync_job=GitHubNormalizationSyncJobRead.model_validate(result["sync_job"]),
        counts=counts,
        status=result["sync_job"]["status"],
        message=message,
        capability_mode="local_normalization",
        is_live=False,
        provider_sync_started=False,
        local_normalization_performed=True,
        persistence_mode=result["persistence_mode"],
        warnings=result["warnings"],
    )


@router.post(
    "/repositories/issues/sync",
    response_model=GitHubSelectedIssueSyncResponse,
)
async def run_selected_repository_issue_sync(
    workspace_id: UUID,
    payload: GitHubSelectedIssueSyncRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubSelectedIssueSyncResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_selected_repository_issues(
                session,
                workspace_id=workspace_id,
                input_payload=GitHubSelectedIssueSyncInput(
                    connection_id=payload.connection_id,
                    repositories=payload.repositories,
                    states=payload.states,
                ),
                requested_by=access.actor.auth_mode,
            )
            await session.commit()
        except GitHubSelectedIssueSyncNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedIssueSyncConflictError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedIssueSyncProviderReadError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedIssueSyncError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubSelectedIssueSyncResponse.model_validate(result)


@router.post(
    "/repositories/pull-requests/sync",
    response_model=GitHubSelectedPullRequestSyncResponse,
)
async def run_selected_repository_pull_request_sync(
    workspace_id: UUID,
    payload: GitHubSelectedPullRequestSyncRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> GitHubSelectedPullRequestSyncResponse:
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_selected_repository_pull_requests(
                session,
                workspace_id=workspace_id,
                input_payload=GitHubSelectedPRSyncInput(
                    connection_id=payload.connection_id,
                    repositories=payload.repositories,
                    states=payload.states,
                ),
                requested_by=access.actor.auth_mode,
            )
            await session.commit()
        except GitHubSelectedPRSyncNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedPRSyncConflictError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedPRSyncProviderReadError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=exc.detail,
            ) from exc
        except GitHubSelectedPRSyncError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return GitHubSelectedPullRequestSyncResponse.model_validate(result)


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
