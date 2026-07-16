from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED,
    ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED,
    ACTION_EXECUTION_EVENT_STATUS_RECORDED,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_FAILED,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_PROPOSAL_STATUS_REJECTED,
    ActionExecutionEvent,
    ActionProposal,
)
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    USER_STATUS_ACTIVE,
    Membership,
    User,
)
from app.services.action_execution_audit_service import (
    append_execution_event,
    get_execution_event_by_idempotency_key,
    local_decision_event_idempotency_key,
    stable_digest,
)
from app.services.action_proposal_service import action_proposal_version
from app.services.headquarters_read_service import (
    HeadquartersAccessChangedError,
    read_workspace_headquarters,
)
from app.services.identity_service import role_allows


Decision = Literal["approved", "rejected"]


class ActionProposalDecisionError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ActionProposalDecisionNotFoundError(ActionProposalDecisionError):
    pass


class ActionProposalDecisionForbiddenError(ActionProposalDecisionError):
    pass


class ActionProposalDecisionConflictError(ActionProposalDecisionError):
    pass


@dataclass(frozen=True)
class ActionProposalDecisionCommand:
    decision: Decision
    idempotency_key: str
    proposal_version: str
    expected_snapshot_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ActionProposalDecisionResult:
    proposal: ActionProposal
    event: ActionExecutionEvent
    decision: Decision
    replayed: bool
    proposal_version: str


async def decide_action_proposal(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    actor_user_id: UUID,
    command: ActionProposalDecisionCommand,
) -> ActionProposalDecisionResult:
    """Record one version-bound, idempotent local proposal decision.

    The command never creates an ActionExecution and never calls a provider.
    Membership and role are checked again in this write session, and the exact
    proposal row is locked before transition or replay resolution.
    """

    await _require_current_admin(
        session,
        workspace_id=workspace_id,
        user_id=actor_user_id,
    )
    proposal = await session.scalar(
        select(ActionProposal)
        .where(
            ActionProposal.workspace_id == workspace_id,
            ActionProposal.id == proposal_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise ActionProposalDecisionNotFoundError("action proposal not found")

    audit_idempotency_key = local_decision_event_idempotency_key(
        workspace_id=workspace_id,
        action_proposal_id=proposal_id,
        client_idempotency_key=command.idempotency_key,
    )
    request_fingerprint = _decision_request_fingerprint(command)
    existing_event = await get_execution_event_by_idempotency_key(
        session,
        idempotency_key=audit_idempotency_key,
    )
    if existing_event is not None:
        return _replayed_result(
            proposal=proposal,
            event=existing_event,
            command=command,
            request_fingerprint=request_fingerprint,
        )

    if proposal.status != ACTION_PROPOSAL_STATUS_PROPOSED:
        raise ActionProposalDecisionConflictError(
            "action proposal is not in proposed status"
        )
    current_version = action_proposal_version(proposal)
    if current_version != command.proposal_version:
        raise ActionProposalDecisionConflictError("action proposal version changed")

    await _validate_expected_headquarters_context(
        workspace_id=workspace_id,
        proposal_id=proposal_id,
        actor_user_id=actor_user_id,
        expected_snapshot_id=command.expected_snapshot_id,
        proposal_version=current_version,
    )

    decided_at = datetime.now(timezone.utc)
    if command.decision == ACTION_PROPOSAL_STATUS_APPROVED:
        proposal.status = ACTION_PROPOSAL_STATUS_APPROVED
        proposal.approved_by_user_id = actor_user_id
        proposal.approved_at = decided_at
        event_type = ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
    else:
        proposal.status = ACTION_PROPOSAL_STATUS_REJECTED
        proposal.rejected_by_user_id = actor_user_id
        proposal.rejected_at = decided_at
        proposal.rejection_reason = _optional_text(command.reason)
        event_type = ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED
    await session.flush()
    await session.refresh(proposal)

    event = await append_execution_event(
        session,
        workspace_id=workspace_id,
        action_proposal_id=proposal_id,
        event_type=event_type,
        actor="workspace_admin",
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=(
            f"Action proposal {command.decision} locally. "
            "No external write occurred."
        ),
        idempotency_key=audit_idempotency_key,
        provider=proposal.target_provider,
        action=proposal.action_type,
        external_execution_enabled=False,
        confirmation_received=False,
        event_metadata={
            "bulk": False,
            "decision": command.decision,
            "decision_contract": "local-decision.v1",
            "expected_snapshot_id": command.expected_snapshot_id,
            "external_execution_enabled": False,
            "external_write_performed": False,
            "proposal_status": proposal.status,
            "proposal_version": current_version,
            "request_fingerprint": request_fingerprint,
        },
    )
    return ActionProposalDecisionResult(
        proposal=proposal,
        event=event,
        decision=command.decision,
        replayed=False,
        proposal_version=current_version,
    )


async def _require_current_admin(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    row = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == user_id,
            )
            .with_for_update(of=(Membership, User))
        )
    ).one_or_none()
    if row is None:
        raise ActionProposalDecisionNotFoundError("workspace not found")
    membership, user = row
    if user.status != USER_STATUS_ACTIVE:
        raise ActionProposalDecisionForbiddenError("user disabled")
    if not role_allows(membership.role, MEMBERSHIP_ROLE_ADMIN):
        raise ActionProposalDecisionForbiddenError("insufficient workspace role")


async def _validate_expected_headquarters_context(
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    actor_user_id: UUID,
    expected_snapshot_id: str | None,
    proposal_version: str,
) -> None:
    if expected_snapshot_id is None:
        return
    try:
        headquarters = await read_workspace_headquarters(
            workspace_id=workspace_id,
            user_id=actor_user_id,
        )
    except HeadquartersAccessChangedError as exc:
        raise ActionProposalDecisionNotFoundError("workspace not found") from exc
    if headquarters["snapshot"]["id"] != expected_snapshot_id:
        raise ActionProposalDecisionConflictError("headquarters snapshot changed")

    exact_mission = next(
        (
            mission
            for mission in [headquarters.get("priority"), *headquarters.get("queue", [])]
            if isinstance(mission, dict)
            and mission.get("id") == f"proposal:{proposal_id}"
            and mission.get("kind") == "review_proposal"
            and mission.get("reference_type") == "proposal"
            and mission.get("reference_id") == str(proposal_id)
            and str(mission.get("proposal_id")) == str(proposal_id)
        ),
        None,
    )
    if exact_mission is None:
        raise ActionProposalDecisionConflictError(
            "proposal is not an active headquarters mission"
        )
    if exact_mission.get("proposal_version") != proposal_version:
        raise ActionProposalDecisionConflictError("action proposal version changed")


def _replayed_result(
    *,
    proposal: ActionProposal,
    event: ActionExecutionEvent,
    command: ActionProposalDecisionCommand,
    request_fingerprint: str,
) -> ActionProposalDecisionResult:
    metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
    expected_event_type = (
        ACTION_EXECUTION_EVENT_PROPOSAL_APPROVED
        if command.decision == ACTION_PROPOSAL_STATUS_APPROVED
        else ACTION_EXECUTION_EVENT_PROPOSAL_REJECTED
    )
    expected_statuses = (
        {
            ACTION_PROPOSAL_STATUS_APPROVED,
            ACTION_PROPOSAL_STATUS_EXECUTED,
            ACTION_PROPOSAL_STATUS_FAILED,
        }
        if command.decision == ACTION_PROPOSAL_STATUS_APPROVED
        else {ACTION_PROPOSAL_STATUS_REJECTED}
    )
    if (
        event.event_type != expected_event_type
        or event.workspace_id != proposal.workspace_id
        or event.action_proposal_id != proposal.id
        or metadata.get("request_fingerprint") != request_fingerprint
        or metadata.get("decision") != command.decision
        or proposal.status not in expected_statuses
    ):
        raise ActionProposalDecisionConflictError(
            "idempotency key was already used with different decision input"
        )
    persisted_version = metadata.get("proposal_version")
    if not isinstance(persisted_version, str) or persisted_version != command.proposal_version:
        raise ActionProposalDecisionConflictError(
            "idempotency key was already used with different decision input"
        )
    return ActionProposalDecisionResult(
        proposal=proposal,
        event=event,
        decision=command.decision,
        replayed=True,
        proposal_version=persisted_version,
    )


def _decision_request_fingerprint(command: ActionProposalDecisionCommand) -> str:
    return stable_digest(
        {
            "decision": command.decision,
            "expected_snapshot_id": command.expected_snapshot_id,
            "proposal_version": command.proposal_version,
            "reason": _optional_text(command.reason),
        }
    )


def _optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
