from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
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
from app.services.github_issue_execution_service import (
    GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND,
    GitHubIssueExecutionConflictError,
    GitHubIssueExecutionError,
    GitHubIssueExecutionInput,
    GitHubIssueExecutionNotFoundError,
    GitHubIssueProviderExecutionError,
    execute_approved_github_issue_action,
)

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/actions", tags=["actions"])


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


class ActionProposalExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connection_id: UUID
    confirm_external_write: bool = False
    idempotency_key: str | None = Field(default=None, max_length=255)


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


class ActionExecutionResponse(BaseModel):
    proposal: ExecutedActionProposalRead
    execution: ActionExecutionRead
    is_live: bool
    external_write_performed: bool
    provider: str
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
            await session.rollback()
            status_code = (
                status.HTTP_404_NOT_FOUND
                if exc.detail == GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND
                else status.HTTP_404_NOT_FOUND
            )
            raise HTTPException(status_code=status_code, detail=exc.detail) from exc
        except GitHubIssueExecutionConflictError as exc:
            await session.rollback()
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
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=exc.detail,
            ) from exc
    return ActionExecutionResponse.model_validate(result)


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
