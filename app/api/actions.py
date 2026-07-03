from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.action_models import (
    ACTION_EXECUTION_EVENT_CONFIRMATION_MISSING,
    ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED_BUT_DISABLED,
    ACTION_EXECUTION_EVENT_PREVIEW_BLOCKED,
    ACTION_EXECUTION_EVENT_PREVIEW_GENERATED,
    ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED,
    ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED,
    ACTION_EXECUTION_EVENT_STATUS_BLOCKED,
    ACTION_EXECUTION_EVENT_STATUS_RECORDED,
    ACTION_EXECUTION_EVENT_STATUS_UNSUPPORTED,
    ACTION_EXECUTION_EVENT_UNSUPPORTED,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ACTION_TYPE_INTERNAL_TODO,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_ADMIN, MEMBERSHIP_ROLE_MEMBER
from app.services.action_proposal_service import (
    ACTION_PROPOSAL_APPROVAL_WARNING,
    ACTION_PROPOSAL_NOT_FOUND,
    ACTION_PROPOSAL_NO_EXECUTION_WARNING,
    ActionProposalCreateInput,
    ActionProposalError,
    ActionProposalFilters,
    ActionProposalNotFoundError,
    ActionProposalTransitionError,
    approve_action_proposal,
    create_action_proposal,
    get_action_proposal,
    list_action_proposals,
    reject_action_proposal,
    serialize_action_proposal,
)
from app.services.action_execution_audit_service import (
    append_execution_event,
    execution_event_idempotency_key,
    list_execution_events,
    serialize_execution_event,
    stable_digest,
)
from app.services.github_issue_execution_service import (
    GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND,
    GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_APPROVED,
    GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION,
    GitHubIssueExecutionConflictError,
    GitHubIssueExecutionError,
    GitHubIssueExecutionInput,
    GitHubIssueExecutionNotFoundError,
    GitHubIssueProviderExecutionError,
    execute_approved_github_issue_action,
    validate_github_issue_payload,
)
from app.services.github_execution_result_sync_service import (
    GitHubExecutionResultSyncConflictError,
    GitHubExecutionResultSyncError,
    GitHubExecutionResultSyncInput,
    GitHubExecutionResultSyncNotFoundError,
    GitHubExecutionResultSyncProviderReadError,
    sync_github_issue_execution_result,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/actions", tags=["actions"])

ACTION_EXECUTION_DISABLED_DETAIL = "external execution is disabled"
ACTION_EXECUTION_PREVIEW_WARNING = (
    "Execution preview is dry-run only and does not call GitHub."
)
ACTION_EXECUTION_NO_EVIDENCE_WARNING = (
    "Proposal has no evidence refs; preview preserves that absence."
)
REPO_AUDIT_IMPORT_WARNING = (
    "Repo-audit import created local ActionProposal rows only; no provider calls, "
    "external writes, or LLM calls were started."
)
REPO_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SECRET_TEXT_RE = re.compile(
    r"\b(token|password|secret|api[_-]?key|private[_-]?key)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


class ActionProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    briefing_item_id: UUID | None = None
    target_provider: str = Field(max_length=40)
    action_type: str = Field(max_length=80)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    created_by: str = Field(default="user", max_length=20)


class ActionProposalRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=1000)


class ActionProposalBulkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_ids: list[UUID] = Field(min_length=1, max_length=100)


class ActionProposalBulkRejectRequest(ActionProposalBulkRequest):
    reason: str | None = Field(default=None, max_length=1000)


class RepoAuditImportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    repository_full_name: str = Field(default="", max_length=160)
    title: str | None = Field(default=None, max_length=500)
    summary: str = Field(default="External audit finding.", max_length=2000)
    severity: str | None = Field(default=None, max_length=40)
    risks: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    recommended_next_step: str | None = Field(default=None, max_length=1000)
    area_candidate: str | None = Field(default=None, max_length=80)


class RepoAuditImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[RepoAuditImportFinding] = Field(min_length=1, max_length=50)


class ActionProposalExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    confirm_external_write: bool = False
    idempotency_key: str | None = Field(default=None, max_length=255)


class ActionProposalExecutionResultSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: UUID | None = None


class ActionProposalRead(BaseModel):
    id: UUID
    workspace_id: UUID
    briefing_item_id: UUID | None = None
    target_provider: str
    action_type: str
    title: str
    description: str | None = None
    payload: dict[str, Any]
    status: str
    evidence_refs: list[dict[str, Any]]
    created_by: str
    created_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalListResponse(BaseModel):
    proposals: list[ActionProposalRead]
    count: int
    is_live: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalMutationResponse(BaseModel):
    proposal: ActionProposalRead
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ActionProposalBulkFailureRead(BaseModel):
    proposal_id: UUID
    status_code: int
    detail: str


class ActionProposalBulkResponse(BaseModel):
    proposals: list[ActionProposalRead]
    failures: list[ActionProposalBulkFailureRead]
    succeeded_count: int
    failed_count: int
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class RepoAuditImportFailureRead(BaseModel):
    index: int
    repository_full_name: str | None = None
    status_code: int
    detail: str


class RepoAuditImportResponse(BaseModel):
    proposals: list[ActionProposalRead]
    failures: list[RepoAuditImportFailureRead]
    succeeded_count: int
    failed_count: int
    is_live: bool
    execution_started: bool
    warnings: list[str] = Field(default_factory=list)


class ExecutedActionProposalRead(BaseModel):
    id: UUID
    status: str


class ActionExecutionRead(BaseModel):
    id: UUID
    status: str
    external_id: str | None = None
    provider_response: dict[str, Any]
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ActionExecutionReceiptRead(BaseModel):
    provider: str | None = None
    action: str | None = None
    status: str | None = None
    external_execution_enabled: bool = False
    confirmation_received: bool = False
    external_result_id: str | None = None
    external_result_url: str | None = None
    external_write_performed: bool = False
    provider_result: str = "none"
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ActionExecutionResponse(BaseModel):
    proposal: ExecutedActionProposalRead
    execution: ActionExecutionRead
    receipt: ActionExecutionReceiptRead
    is_live: bool
    external_write_performed: bool
    provider: str
    warnings: list[str] = Field(default_factory=list)


class ActionExecutionCapabilitiesRead(BaseModel):
    dry_run: bool
    local_approval: bool
    external_execution: bool
    live_provider_write: bool
    requires_confirmation: bool


class GitHubIssueExecutionPreviewRead(BaseModel):
    provider: str
    action: str
    repository: str
    title: str
    body: str | None = None
    labels: list[str] = Field(default_factory=list)
    assignees: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class ActionExecutionAuditEventRead(BaseModel):
    id: UUID
    event_type: str
    event: str
    actor: str
    status: str
    created_at: datetime
    message: str
    event_metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    action: str | None = None
    external_execution_enabled: bool = False
    confirmation_received: bool = False
    external_result_id: str | None = None
    external_result_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ActionExecutionPreviewResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    status: str
    mode: str
    message: str
    capabilities: ActionExecutionCapabilitiesRead
    preview: GitHubIssueExecutionPreviewRead | None = None
    audit: list[ActionExecutionAuditEventRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ActionExecutionAuditResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    events: list[ActionExecutionAuditEventRead]
    receipt: ActionExecutionReceiptRead


class ActionExecutionResultSyncIssueRead(BaseModel):
    number: int
    state: str | None = None
    title: str | None = None


class ActionExecutionResultSyncJobRead(BaseModel):
    id: UUID
    status: str
    records_seen: int
    records_created: int
    records_updated: int


class ActionExecutionResultCanonicalRead(BaseModel):
    task_id: UUID | None = None
    source_record_id: UUID | None = None
    external_id: str | None = None
    evidence_refs_count: int = 0


class ActionExecutionResultSyncResponse(BaseModel):
    workspace_id: UUID
    proposal_id: UUID
    synced: bool
    status: str
    provider: str
    action: str
    repository: str
    issue: ActionExecutionResultSyncIssueRead
    sync_job: ActionExecutionResultSyncJobRead
    canonical: ActionExecutionResultCanonicalRead
    counts: dict[str, int] = Field(default_factory=dict)
    audit: list[ActionExecutionAuditEventRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@router.post(
    "/proposals",
    response_model=ActionProposalMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action_proposal_endpoint(
    workspace_id: UUID,
    payload: ActionProposalCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> ActionProposalMutationResponse:
    async with AsyncSessionLocal() as session:
        try:
            proposal = await create_action_proposal(
                session,
                workspace_id=workspace_id,
                created_by_user_id=access.workspace_membership.user.id,
                payload=ActionProposalCreateInput(
                    briefing_item_id=payload.briefing_item_id,
                    target_provider=payload.target_provider,
                    action_type=payload.action_type,
                    title=payload.title,
                    description=payload.description,
                    payload=payload.payload,
                    evidence_refs=payload.evidence_refs,
                    created_by=payload.created_by,
                ),
            )
            await session.commit()
        except ActionProposalError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return _mutation_response(
        proposal=ActionProposalRead.model_validate(serialize_action_proposal(proposal)),
        warnings=[ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    )


@router.get("/proposals", response_model=ActionProposalListResponse)
async def list_action_proposal_endpoint(
    workspace_id: UUID,
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    target_provider: str | None = Query(default=None, max_length=40),
    action_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ActionProposalListResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        proposals = await list_action_proposals(
            session,
            workspace_id=workspace_id,
            filters=ActionProposalFilters(
                status=status_filter,
                target_provider=target_provider,
                action_type=action_type,
                limit=limit,
            ),
        )
    return ActionProposalListResponse(
        proposals=[
            ActionProposalRead.model_validate(serialize_action_proposal(proposal))
            for proposal in proposals
        ],
        count=len(proposals),
        is_live=False,
        warnings=[ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    )


@router.post(
    "/proposals/import-repo-audit",
    response_model=RepoAuditImportResponse,
)
async def import_repo_audit_action_proposals_endpoint(
    workspace_id: UUID,
    payload: RepoAuditImportRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_MEMBER)),
) -> RepoAuditImportResponse:
    proposals: list[ActionProposalRead] = []
    failures: list[RepoAuditImportFailureRead] = []
    async with AsyncSessionLocal() as session:
        for index, finding in enumerate(payload.findings):
            try:
                action_input = _repo_audit_import_action_input(finding)
                proposal = await create_action_proposal(
                    session,
                    workspace_id=workspace_id,
                    created_by_user_id=access.workspace_membership.user.id,
                    payload=action_input,
                )
                proposals.append(
                    ActionProposalRead.model_validate(
                        serialize_action_proposal(proposal)
                    )
                )
            except ActionProposalError as exc:
                failures.append(
                    RepoAuditImportFailureRead(
                        index=index,
                        repository_full_name=finding.repository_full_name,
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=exc.detail,
                    )
                )
        await session.commit()

    return RepoAuditImportResponse(
        proposals=proposals,
        failures=failures,
        succeeded_count=len(proposals),
        failed_count=len(failures),
        is_live=False,
        execution_started=False,
        warnings=[REPO_AUDIT_IMPORT_WARNING, ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    )


@router.post(
    "/proposals/bulk-approve",
    response_model=ActionProposalBulkResponse,
)
async def bulk_approve_action_proposals_endpoint(
    workspace_id: UUID,
    payload: ActionProposalBulkRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionProposalBulkResponse:
    async with AsyncSessionLocal() as session:
        proposals: list[ActionProposalRead] = []
        failures: list[ActionProposalBulkFailureRead] = []
        for proposal_id in _unique_proposal_ids(payload.proposal_ids):
            try:
                proposal = await approve_action_proposal(
                    session,
                    workspace_id=workspace_id,
                    proposal_id=proposal_id,
                    approved_by_user_id=access.workspace_membership.user.id,
                )
                await _record_local_review_event(
                    session,
                    proposal=proposal,
                    event_type=ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED,
                    decision="approved",
                    bulk=True,
                )
                proposals.append(
                    ActionProposalRead.model_validate(
                        serialize_action_proposal(proposal)
                    )
                )
            except ActionProposalNotFoundError as exc:
                failures.append(
                    ActionProposalBulkFailureRead(
                        proposal_id=proposal_id,
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=exc.detail,
                    )
                )
            except ActionProposalTransitionError as exc:
                failures.append(
                    ActionProposalBulkFailureRead(
                        proposal_id=proposal_id,
                        status_code=status.HTTP_409_CONFLICT,
                        detail=exc.detail,
                    )
                )
        await session.commit()

    warnings = [ACTION_PROPOSAL_NO_EXECUTION_WARNING]
    if proposals:
        warnings.insert(0, ACTION_PROPOSAL_APPROVAL_WARNING)
    return _bulk_response(proposals=proposals, failures=failures, warnings=warnings)


@router.post(
    "/proposals/bulk-reject",
    response_model=ActionProposalBulkResponse,
)
async def bulk_reject_action_proposals_endpoint(
    workspace_id: UUID,
    payload: ActionProposalBulkRejectRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionProposalBulkResponse:
    async with AsyncSessionLocal() as session:
        proposals: list[ActionProposalRead] = []
        failures: list[ActionProposalBulkFailureRead] = []
        for proposal_id in _unique_proposal_ids(payload.proposal_ids):
            try:
                proposal = await reject_action_proposal(
                    session,
                    workspace_id=workspace_id,
                    proposal_id=proposal_id,
                    rejected_by_user_id=access.workspace_membership.user.id,
                    reason=payload.reason,
                )
                await _record_local_review_event(
                    session,
                    proposal=proposal,
                    event_type=ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED,
                    decision="rejected",
                    bulk=True,
                )
                proposals.append(
                    ActionProposalRead.model_validate(
                        serialize_action_proposal(proposal)
                    )
                )
            except ActionProposalNotFoundError as exc:
                failures.append(
                    ActionProposalBulkFailureRead(
                        proposal_id=proposal_id,
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=exc.detail,
                    )
                )
            except ActionProposalTransitionError as exc:
                failures.append(
                    ActionProposalBulkFailureRead(
                        proposal_id=proposal_id,
                        status_code=status.HTTP_409_CONFLICT,
                        detail=exc.detail,
                    )
                )
        await session.commit()

    return _bulk_response(
        proposals=proposals,
        failures=failures,
        warnings=[ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    )


@router.get("/proposals/{proposal_id}", response_model=ActionProposalRead)
async def get_action_proposal_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ActionProposalRead:
    _ = access
    async with AsyncSessionLocal() as session:
        proposal = await get_action_proposal(
            session,
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ACTION_PROPOSAL_NOT_FOUND,
        )
    return ActionProposalRead.model_validate(serialize_action_proposal(proposal))


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ActionProposalMutationResponse,
)
async def approve_action_proposal_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionProposalMutationResponse:
    async with AsyncSessionLocal() as session:
        try:
            proposal = await approve_action_proposal(
                session,
                workspace_id=workspace_id,
                proposal_id=proposal_id,
                approved_by_user_id=access.workspace_membership.user.id,
            )
            await _record_local_review_event(
                session,
                proposal=proposal,
                event_type=ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED,
                decision="approved",
                bulk=False,
            )
            await session.commit()
        except ActionProposalNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except ActionProposalTransitionError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
    return _mutation_response(
        proposal=ActionProposalRead.model_validate(serialize_action_proposal(proposal)),
        warnings=[
            ACTION_PROPOSAL_APPROVAL_WARNING,
            ACTION_PROPOSAL_NO_EXECUTION_WARNING,
        ],
    )


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ActionProposalMutationResponse,
)
async def reject_action_proposal_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    payload: ActionProposalRejectRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionProposalMutationResponse:
    async with AsyncSessionLocal() as session:
        try:
            proposal = await reject_action_proposal(
                session,
                workspace_id=workspace_id,
                proposal_id=proposal_id,
                rejected_by_user_id=access.workspace_membership.user.id,
                reason=payload.reason,
            )
            await _record_local_review_event(
                session,
                proposal=proposal,
                event_type=ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED,
                decision="rejected",
                bulk=False,
            )
            await session.commit()
        except ActionProposalNotFoundError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except ActionProposalTransitionError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
    return _mutation_response(
        proposal=ActionProposalRead.model_validate(serialize_action_proposal(proposal)),
        warnings=[ACTION_PROPOSAL_NO_EXECUTION_WARNING],
    )


@router.get(
    "/proposals/{proposal_id}/execution-preview",
    response_model=ActionExecutionPreviewResponse,
)
async def preview_action_proposal_execution_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ActionExecutionPreviewResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        proposal = await get_action_proposal(
            session,
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ACTION_PROPOSAL_NOT_FOUND,
            )
        response = _execution_preview_response(proposal)
        await _record_preview_event(
            session,
            proposal=proposal,
            response=response,
            external_execution_enabled=bool(settings.enable_write_actions),
        )
        events = await list_execution_events(
            session,
            workspace_id=workspace_id,
            action_proposal_id=proposal_id,
        )
        await session.commit()
    response.audit = _audit_event_reads(events)
    return response


@router.get(
    "/proposals/{proposal_id}/audit",
    response_model=ActionExecutionAuditResponse,
)
async def get_action_proposal_audit_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> ActionExecutionAuditResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        proposal = await get_action_proposal(
            session,
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ACTION_PROPOSAL_NOT_FOUND,
            )
        events = await list_execution_events(
            session,
            workspace_id=workspace_id,
            action_proposal_id=proposal_id,
        )
    return ActionExecutionAuditResponse(
        workspace_id=workspace_id,
        proposal_id=proposal_id,
        events=_audit_event_reads(events),
        receipt=_receipt_from_events(events),
    )


@router.post(
    "/proposals/{proposal_id}/sync-execution-result",
    response_model=ActionExecutionResultSyncResponse,
)
async def sync_action_proposal_execution_result_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    payload: ActionProposalExecutionResultSyncRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionExecutionResultSyncResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_github_issue_execution_result(
                session,
                workspace_id=workspace_id,
                proposal_id=proposal_id,
                input_payload=GitHubExecutionResultSyncInput(
                    connection_id=payload.connection_id,
                ),
            )
            await session.commit()
        except GitHubExecutionResultSyncNotFoundError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.detail,
            ) from exc
        except GitHubExecutionResultSyncConflictError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
        except GitHubExecutionResultSyncProviderReadError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=exc.detail,
            ) from exc
        except GitHubExecutionResultSyncError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return ActionExecutionResultSyncResponse.model_validate(result)


@router.post(
    "/proposals/{proposal_id}/execute",
    response_model=ActionExecutionResponse,
)
async def execute_action_proposal_endpoint(
    workspace_id: UUID,
    proposal_id: UUID,
    payload: ActionProposalExecuteRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> ActionExecutionResponse:
    _ = access
    async with AsyncSessionLocal() as session:
        proposal = await get_action_proposal(
            session,
            workspace_id=workspace_id,
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ACTION_PROPOSAL_NOT_FOUND,
            )
        if payload.confirm_external_write is not True:
            await _record_execute_block_event(
                session,
                proposal=proposal,
                event_type=ACTION_EXECUTION_EVENT_CONFIRMATION_MISSING,
                message="Execution blocked because confirm_external_write was not true.",
                confirmation_received=False,
                external_execution_enabled=bool(settings.enable_write_actions),
                error_code="confirmation_missing",
                error_message="confirm_external_write must be true",
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="confirm_external_write must be true",
            )
        if not settings.enable_write_actions:
            await _record_execute_block_event(
                session,
                proposal=proposal,
                event_type=ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED_BUT_DISABLED,
                message=(
                    "Execution confirmation was received, but external execution "
                    "is disabled in this environment. No external write occurred."
                ),
                confirmation_received=True,
                external_execution_enabled=False,
                error_code="external_execution_disabled",
                error_message=ACTION_EXECUTION_DISABLED_DETAIL,
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ACTION_EXECUTION_DISABLED_DETAIL,
            )

    async with AsyncSessionLocal() as session:
        try:
            result = await execute_approved_github_issue_action(
                session,
                workspace_id=workspace_id,
                proposal_id=proposal_id,
                input_payload=GitHubIssueExecutionInput(
                    connection_id=payload.connection_id,
                    confirm_external_write=payload.confirm_external_write,
                    idempotency_key=payload.idempotency_key,
                ),
            )
            await session.commit()
        except GitHubIssueExecutionNotFoundError as exc:
            await session.commit()
            status_code = (
                status.HTTP_404_NOT_FOUND
                if exc.detail == GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND
                else status.HTTP_404_NOT_FOUND
            )
            raise HTTPException(status_code=status_code, detail=exc.detail) from exc
        except GitHubIssueExecutionConflictError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.detail,
            ) from exc
        except GitHubIssueProviderExecutionError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=exc.detail,
            ) from exc
        except GitHubIssueExecutionError as exc:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return ActionExecutionResponse.model_validate(result)


async def _record_preview_event(
    session: Any,
    *,
    proposal: Any,
    response: ActionExecutionPreviewResponse,
    external_execution_enabled: bool,
) -> None:
    preview_hash = _preview_hash(proposal=proposal, response=response)
    await append_execution_event(
        session,
        workspace_id=proposal.workspace_id,
        action_proposal_id=proposal.id,
        event_type=_preview_event_type(response.status),
        actor="system",
        status=_preview_event_status(response.status),
        message=f"{response.message} No external write occurred.",
        idempotency_key=execution_event_idempotency_key(
            workspace_id=proposal.workspace_id,
            action_proposal_id=proposal.id,
            event_type=_preview_event_type(response.status),
            external_execution_enabled=external_execution_enabled,
            confirmation_received=False,
            preview_hash=preview_hash,
        ),
        provider=response.preview.provider if response.preview else proposal.target_provider,
        action=response.preview.action if response.preview else proposal.action_type,
        external_execution_enabled=external_execution_enabled,
        confirmation_received=False,
        event_metadata=_preview_event_metadata(
            proposal=proposal,
            response=response,
            preview_hash=preview_hash,
        ),
        error_code=None if response.status == "preview_ready" else _audit_error_code(response.message),
        error_message=None if response.status == "preview_ready" else response.message,
    )


async def _record_execute_block_event(
    session: Any,
    *,
    proposal: Any,
    event_type: str,
    message: str,
    confirmation_received: bool,
    external_execution_enabled: bool,
    error_code: str,
    error_message: str,
) -> None:
    await append_execution_event(
        session,
        workspace_id=proposal.workspace_id,
        action_proposal_id=proposal.id,
        event_type=event_type,
        actor="workspace_admin",
        status=ACTION_EXECUTION_EVENT_STATUS_BLOCKED,
        message=f"{message} No external write occurred.",
        idempotency_key=execution_event_idempotency_key(
            workspace_id=proposal.workspace_id,
            action_proposal_id=proposal.id,
            event_type=event_type,
            external_execution_enabled=external_execution_enabled,
            confirmation_received=confirmation_received,
            reason=error_code,
        ),
        provider=proposal.target_provider,
        action=proposal.action_type,
        external_execution_enabled=external_execution_enabled,
        confirmation_received=confirmation_received,
        event_metadata={
            "confirmation_received": confirmation_received,
            "external_execution_enabled": external_execution_enabled,
            "proposal_status": proposal.status,
        },
        error_code=error_code,
        error_message=error_message,
    )


async def _record_local_review_event(
    session: Any,
    *,
    proposal: Any,
    event_type: str,
    decision: str,
    bulk: bool,
) -> None:
    decided_at = (
        proposal.approved_at
        if decision == "approved"
        else proposal.rejected_at
    ) or proposal.updated_at
    await append_execution_event(
        session,
        workspace_id=proposal.workspace_id,
        action_proposal_id=proposal.id,
        event_type=event_type,
        actor="workspace_admin",
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=(
            f"Action proposal {decision} locally. "
            "No external write occurred."
        ),
        idempotency_key=execution_event_idempotency_key(
            workspace_id=proposal.workspace_id,
            action_proposal_id=proposal.id,
            event_type=event_type,
            external_execution_enabled=False,
            confirmation_received=False,
            reason=f"{decision}:{decided_at}:{'bulk' if bulk else 'single'}",
        ),
        provider=proposal.target_provider,
        action=proposal.action_type,
        external_execution_enabled=False,
        confirmation_received=False,
        event_metadata={
            "bulk": bulk,
            "decision": decision,
            "external_execution_enabled": False,
            "proposal_status": proposal.status,
        },
    )


def _execution_preview_response(proposal: Any) -> ActionExecutionPreviewResponse:
    is_external_enabled = bool(settings.enable_write_actions)
    warnings = [ACTION_EXECUTION_PREVIEW_WARNING]
    if not proposal.evidence_refs:
        warnings.append(ACTION_EXECUTION_NO_EVIDENCE_WARNING)

    capabilities = _execution_capabilities(
        dry_run=False,
        external_execution_enabled=is_external_enabled,
    )
    mode = "dry_run" if is_external_enabled else "external_disabled"
    if proposal.status != ACTION_PROPOSAL_STATUS_APPROVED:
        return ActionExecutionPreviewResponse(
            workspace_id=proposal.workspace_id,
            proposal_id=proposal.id,
            status="not_approved",
            mode=mode,
            message=GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_APPROVED,
            capabilities=capabilities,
            warnings=warnings,
        )
    if (
        proposal.target_provider != ACTION_TARGET_PROVIDER_GITHUB
        or proposal.action_type != ACTION_TYPE_CREATE_GITHUB_ISSUE
    ):
        return ActionExecutionPreviewResponse(
            workspace_id=proposal.workspace_id,
            proposal_id=proposal.id,
            status="unsupported",
            mode=mode,
            message=GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION,
            capabilities=capabilities,
            warnings=warnings,
        )

    try:
        issue_payload = validate_github_issue_payload(proposal.payload or {})
    except GitHubIssueExecutionError as exc:
        return ActionExecutionPreviewResponse(
            workspace_id=proposal.workspace_id,
            proposal_id=proposal.id,
            status="blocked",
            mode=mode,
            message=exc.detail,
            capabilities=capabilities,
            warnings=warnings,
        )

    return ActionExecutionPreviewResponse(
        workspace_id=proposal.workspace_id,
        proposal_id=proposal.id,
        status="preview_ready",
        mode=mode,
        message=(
            "Preview ready. Live GitHub write requires explicit confirmation."
            if is_external_enabled
            else "Preview ready. External execution is disabled in this environment."
        ),
        capabilities=_execution_capabilities(
            dry_run=True,
            external_execution_enabled=is_external_enabled,
        ),
        preview=GitHubIssueExecutionPreviewRead(
            provider=ACTION_TARGET_PROVIDER_GITHUB,
            action=ACTION_TYPE_CREATE_GITHUB_ISSUE,
            repository=issue_payload.repository_full_name,
            title=issue_payload.title,
            body=issue_payload.body,
            labels=issue_payload.labels,
            assignees=issue_payload.assignees,
            evidence_refs=proposal.evidence_refs or [],
        ),
        warnings=warnings,
    )


def _execution_capabilities(
    *,
    dry_run: bool,
    external_execution_enabled: bool,
) -> ActionExecutionCapabilitiesRead:
    return ActionExecutionCapabilitiesRead(
        dry_run=dry_run,
        local_approval=True,
        external_execution=external_execution_enabled,
        live_provider_write=external_execution_enabled,
        requires_confirmation=True,
    )


def _audit_event_reads(events: list[Any]) -> list[ActionExecutionAuditEventRead]:
    return [
        ActionExecutionAuditEventRead.model_validate(serialize_execution_event(event))
        for event in events
    ]


def _receipt_from_events(events: list[Any]) -> ActionExecutionReceiptRead:
    if not events:
        return ActionExecutionReceiptRead()
    latest = events[-1]
    receipt_event = next(
        (
            event
            for event in reversed(events)
            if not str(event.event_type).startswith("execution_result_sync_")
            if event.external_result_id
            or event.external_result_url
            or event.error_code
            or event.error_message
        ),
        latest,
    )
    has_external_result = bool(
        receipt_event.external_result_id or receipt_event.external_result_url
    )
    provider_result = "none"
    status_value: str | None = None
    if has_external_result:
        provider_result = "succeeded"
        status_value = "succeeded"
    elif receipt_event.error_code or receipt_event.error_message:
        provider_result = "failed"
        status_value = "failed"
    return ActionExecutionReceiptRead(
        provider=receipt_event.provider,
        action=receipt_event.action,
        status=status_value,
        external_execution_enabled=receipt_event.external_execution_enabled,
        confirmation_received=receipt_event.confirmation_received,
        external_result_id=receipt_event.external_result_id,
        external_result_url=receipt_event.external_result_url,
        external_write_performed=has_external_result,
        provider_result=provider_result,
        error_code=receipt_event.error_code,
        error_message=receipt_event.error_message,
        created_at=receipt_event.created_at,
        updated_at=receipt_event.created_at,
    )


def _preview_event_type(response_status: str) -> str:
    if response_status == "preview_ready":
        return ACTION_EXECUTION_EVENT_PREVIEW_GENERATED
    if response_status == "unsupported":
        return ACTION_EXECUTION_EVENT_UNSUPPORTED
    return ACTION_EXECUTION_EVENT_PREVIEW_BLOCKED


def _preview_event_status(response_status: str) -> str:
    if response_status == "preview_ready":
        return ACTION_EXECUTION_EVENT_STATUS_RECORDED
    if response_status == "unsupported":
        return ACTION_EXECUTION_EVENT_STATUS_UNSUPPORTED
    return ACTION_EXECUTION_EVENT_STATUS_BLOCKED


def _preview_hash(
    *,
    proposal: Any,
    response: ActionExecutionPreviewResponse,
) -> str:
    preview = response.preview
    return stable_digest(
        {
            "action": preview.action if preview else proposal.action_type,
            "assignees_count": len(preview.assignees) if preview else 0,
            "evidence_refs_count": len(preview.evidence_refs) if preview else 0,
            "external_execution_enabled": response.capabilities.external_execution,
            "has_body": bool(preview.body) if preview else False,
            "labels_count": len(preview.labels) if preview else 0,
            "message": response.message,
            "mode": response.mode,
            "proposal_updated_at": proposal.updated_at,
            "provider": preview.provider if preview else proposal.target_provider,
            "repository": preview.repository if preview else None,
            "status": response.status,
        }
    )


def _preview_event_metadata(
    *,
    proposal: Any,
    response: ActionExecutionPreviewResponse,
    preview_hash: str,
) -> dict[str, Any]:
    preview = response.preview
    return {
        "action": preview.action if preview else proposal.action_type,
        "assignees_count": len(preview.assignees) if preview else 0,
        "evidence_refs_count": len(preview.evidence_refs) if preview else 0,
        "external_execution_enabled": response.capabilities.external_execution,
        "has_body": bool(preview.body) if preview else False,
        "labels_count": len(preview.labels) if preview else 0,
        "mode": response.mode,
        "preview_hash": preview_hash,
        "provider": preview.provider if preview else proposal.target_provider,
        "status": response.status,
    }


def _audit_error_code(message: str) -> str:
    normalized = message.strip().casefold()
    if "secret-like key" in normalized:
        return "payload_contains_secret_like_key"
    safe = "".join(char if char.isalnum() else "_" for char in normalized)
    return "_".join(part for part in safe.split("_") if part)[:120] or "blocked"


def _mutation_response(
    *,
    proposal: ActionProposalRead,
    warnings: list[str],
) -> ActionProposalMutationResponse:
    return ActionProposalMutationResponse(
        proposal=proposal,
        is_live=False,
        execution_started=False,
        warnings=warnings,
    )


def _bulk_response(
    *,
    proposals: list[ActionProposalRead],
    failures: list[ActionProposalBulkFailureRead],
    warnings: list[str],
) -> ActionProposalBulkResponse:
    return ActionProposalBulkResponse(
        proposals=proposals,
        failures=failures,
        succeeded_count=len(proposals),
        failed_count=len(failures),
        is_live=False,
        execution_started=False,
        warnings=warnings,
    )


def _repo_audit_import_action_input(
    finding: RepoAuditImportFinding,
) -> ActionProposalCreateInput:
    repository_full_name = _redact_import_text(finding.repository_full_name, limit=160)
    if not REPO_FULL_NAME_RE.fullmatch(repository_full_name):
        raise ActionProposalError("repository_full_name must be in owner/repo format")
    evidence_refs = _imported_strings(finding.evidence_refs, limit=500, max_items=50)
    if not evidence_refs:
        raise ActionProposalError("repo-audit import finding requires evidence_refs")
    risks = _imported_strings(finding.risks, limit=120, max_items=20)
    title = _redact_import_text(
        finding.title or f"External repo audit follow-up: {repository_full_name}",
        limit=500,
    )
    summary = _redact_import_text(finding.summary, limit=2000)
    recommended_next_step = _optional_redacted_text(
        finding.recommended_next_step, limit=1000
    )
    area_candidate = _optional_redacted_text(finding.area_candidate, limit=80)
    severity = _optional_redacted_text(finding.severity, limit=40)
    return ActionProposalCreateInput(
        target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
        action_type=ACTION_TYPE_INTERNAL_TODO,
        title=title,
        description=_repo_audit_import_description(
            repository_full_name=repository_full_name,
            summary=summary,
            risks=risks,
            recommended_next_step=recommended_next_step,
        ),
        payload={
            "source": "repo_audit_import",
            "repository_full_name": repository_full_name,
            "severity": severity,
            "area_candidate": area_candidate,
            "recommended_next_step": recommended_next_step,
            "related_entities": risks,
        },
        evidence_refs=[
            {
                "kind": "repo_audit_external",
                "source": "external_repo_audit_import",
                "ref": ref,
                "url": None,
            }
            for ref in evidence_refs
        ],
        created_by="user",
    )


def _repo_audit_import_description(
    *,
    repository_full_name: str,
    summary: str,
    risks: list[str],
    recommended_next_step: str | None,
) -> str:
    parts = [
        f"Репозиторий: {repository_full_name}",
        summary,
    ]
    if recommended_next_step:
        parts.append(f"Рекомендуемый следующий шаг: {recommended_next_step}")
    if risks:
        parts.append(f"Риски: {', '.join(risks)}")
    return "\n".join(parts)


def _imported_strings(
    values: list[str],
    *,
    limit: int,
    max_items: int,
) -> list[str]:
    result: list[str] = []
    for value in values[:max_items]:
        text = _redact_import_text(value, limit=limit)
        if text:
            result.append(text)
    return result


def _optional_redacted_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    text = _redact_import_text(value, limit=limit)
    return text or None


def _redact_import_text(value: str, *, limit: int) -> str:
    return SECRET_TEXT_RE.sub(r"\1=[redacted]", value).strip()[:limit]


def _unique_proposal_ids(proposal_ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    unique_ids: list[UUID] = []
    for proposal_id in proposal_ids:
        if proposal_id in seen:
            continue
        seen.add(proposal_id)
        unique_ids.append(proposal_id)
    return unique_ids
