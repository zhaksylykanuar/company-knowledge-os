from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.action_models import (
    ACTION_EXECUTION_EVENT_BLOCKED,
    ACTION_EXECUTION_EVENT_CLAIMED,
    ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED,
    ACTION_EXECUTION_EVENT_DUPLICATE_RETURNED_EXISTING_RECEIPT,
    ACTION_EXECUTION_EVENT_FAILED,
    ACTION_EXECUTION_EVENT_OUTCOME_UNCERTAIN,
    ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED,
    ACTION_EXECUTION_EVENT_STARTED,
    ACTION_EXECUTION_EVENT_STATUS_BLOCKED,
    ACTION_EXECUTION_EVENT_STATUS_RECORDED,
    ACTION_EXECUTION_EVENT_STATUS_UNSUPPORTED,
    ACTION_EXECUTION_EVENT_SUCCEEDED,
    ACTION_EXECUTION_STATUS_CLAIMED,
    ACTION_EXECUTION_STATUS_FAILED,
    ACTION_EXECUTION_STATUS_RUNNING,
    ACTION_EXECUTION_STATUS_SUCCEEDED,
    ACTION_EXECUTION_STATUS_UNCERTAIN,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ACTION_TYPE_CREATE_GITHUB_ISSUE,
    ActionExecution,
    ActionProposal,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
)
from app.services.action_proposal_service import SECRET_LIKE_KEYS
from app.services.action_execution_audit_service import (
    append_execution_event,
    execution_event_idempotency_key,
)
from app.services.github_issue_client import create_issue
from app.services.headquarters_read_service import (
    ActionProposalEvidenceValidationError,
    validate_action_proposal_evidence,
)
from app.services.real_connector_guard import require_real_connectors_enabled
from app.services.secret_encryption import SecretEncryptionError, decrypt_secret

GITHUB_ISSUE_EXECUTION_CONFIRM_REQUIRED = "confirm_external_write must be true"
GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_FOUND = "action proposal not found"
GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_APPROVED = "action proposal is not approved"
GITHUB_ISSUE_EXECUTION_ALREADY_EXECUTED = "action proposal already executed"
GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION = "unsupported action proposal"
GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND = "github connection not found"
GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_GITHUB = "connection is not a GitHub connection"
GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_CONNECTED = "github connection is not connected"
GITHUB_ISSUE_EXECUTION_TOKEN_MISSING = "github connection has no encrypted access token"
GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE = "github token could not be decrypted"
GITHUB_ISSUE_EXECUTION_EVIDENCE_REQUIRED = (
    "evidence_refs are required for live execution"
)
GITHUB_ISSUE_EXECUTION_ALLOWED_REPOS_REQUIRED = (
    "github write allowed repos are not configured"
)
GITHUB_ISSUE_EXECUTION_REPOSITORY_NOT_ALLOWED = (
    "github repository is not allowed for live execution"
)
GITHUB_ISSUE_EXECUTION_DUPLICATE_RECEIPT = (
    "existing successful execution receipt returned; no external write occurred"
)
GITHUB_ISSUE_EXECUTION_IDEMPOTENCY_REQUIRED = (
    "idempotency_key is required for live execution"
)
GITHUB_ISSUE_EXECUTION_IDEMPOTENCY_REUSED = (
    "idempotency key was already used with different execution input"
)
GITHUB_ISSUE_EXECUTION_IN_PROGRESS = (
    "an execution claim already exists; reconcile it before retrying"
)
GITHUB_ISSUE_EXECUTION_RETRY_KEY_REQUIRED = (
    "the idempotency key already completed without success; use a new key"
)
GITHUB_ISSUE_EXECUTION_OUTCOME_UNCERTAIN = (
    "github issue outcome is uncertain; reconcile before retrying"
)
GITHUB_ISSUE_EXECUTION_BODY_TOO_LARGE = (
    "github issue body is too large for the execution marker"
)
GITHUB_ISSUE_BODY_MAX_BYTES = 65_536


class GitHubIssueExecutionError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GitHubIssueExecutionNotFoundError(GitHubIssueExecutionError):
    pass


class GitHubIssueExecutionConflictError(GitHubIssueExecutionError):
    pass


class GitHubIssueProviderExecutionError(GitHubIssueExecutionError):
    pass


@dataclass(frozen=True)
class GitHubIssueExecutionInput:
    connection_id: UUID
    confirm_external_write: bool
    requested_by_user_id: UUID
    idempotency_key: str


@dataclass(frozen=True)
class GitHubIssuePayload:
    repository_full_name: str
    title: str
    body: str | None
    labels: list[str]
    assignees: list[str]


async def execute_approved_github_issue_action(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    input_payload: GitHubIssueExecutionInput,
) -> dict[str, Any]:
    require_real_connectors_enabled()
    if input_payload.confirm_external_write is not True:
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_CONFIRM_REQUIRED)
    idempotency_key = _required_idempotency_key(input_payload.idempotency_key)

    proposal = await _get_proposal_or_raise(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
        for_update=True,
    )
    request_hash = _execution_request_hash(
        proposal=proposal,
        workspace_id=workspace_id,
        connection_id=input_payload.connection_id,
        requested_by_user_id=input_payload.requested_by_user_id,
    )
    existing_idempotent_execution = await _get_execution_by_idempotency_key(
        session,
        workspace_id=workspace_id,
        idempotency_key=idempotency_key,
    )
    if existing_idempotent_execution is not None:
        return await _resolve_existing_execution(
            session,
            proposal=proposal,
            execution=existing_idempotent_execution,
            request_hash=request_hash,
            actor_user_id=input_payload.requested_by_user_id,
        )

    existing_execution = await _get_active_or_successful_execution(
        session,
        proposal_id=proposal.id,
    )
    if existing_execution is not None:
        return await _resolve_existing_execution(
            session,
            proposal=proposal,
            execution=existing_execution,
            request_hash=None,
            actor_user_id=input_payload.requested_by_user_id,
        )

    try:
        _validate_proposal_for_execution(proposal)
        issue_payload = validate_github_issue_payload(proposal.payload or {})
        _validate_body_marker_capacity(issue_payload.body)
        await _validate_evidence_for_live_execution(
            session,
            workspace_id=workspace_id,
            proposal=proposal,
        )
        _validate_repository_allowlist(issue_payload)
        connection = await _get_connection_or_raise(
            session,
            workspace_id=workspace_id,
            connection_id=input_payload.connection_id,
        )
    except GitHubIssueExecutionError as exc:
        await _append_blocked_execution_event(
            session,
            proposal=proposal,
            detail=exc.detail,
            confirmation_received=True,
            actor_user_id=input_payload.requested_by_user_id,
        )
        raise

    claimed_at = datetime.now(timezone.utc)
    execution = ActionExecution(
        action_proposal_id=proposal.id,
        workspace_id=workspace_id,
        requested_by_user_id=input_payload.requested_by_user_id,
        connection_id=connection.id,
        client_idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=ACTION_EXECUTION_STATUS_CLAIMED,
        claimed_at=claimed_at,
        provider_response={},
    )
    session.add(execution)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        concurrent_execution = (
            await _get_execution_by_idempotency_key(
                session,
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
            )
            or await _get_active_or_successful_execution(
                session,
                proposal_id=proposal_id,
            )
        )
        if concurrent_execution is not None:
            raise GitHubIssueExecutionConflictError(
                GITHUB_ISSUE_EXECUTION_IN_PROGRESS
            ) from exc
        raise

    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_CONFIRMATION_RECEIVED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="Execution confirmation received for approved GitHub issue proposal.",
        confirmation_received=True,
        external_execution_enabled=True,
        reason=f"{execution.id}:confirmation_received",
        actor_user_id=input_payload.requested_by_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "proposal_status": proposal.status,
        },
    )
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_CLAIMED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="A durable execution claim was recorded before the provider request.",
        confirmation_received=True,
        external_execution_enabled=True,
        reason=str(execution.id),
        actor_user_id=input_payload.requested_by_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "claimed_at": claimed_at.isoformat(),
            "request_hash": request_hash,
        },
    )
    await session.commit()

    try:
        access_token = decrypt_secret(connection.encrypted_access_token or "")
    except SecretEncryptionError as exc:
        await _mark_pre_provider_failed(
            session,
            proposal=proposal,
            execution=execution,
            message=GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE,
        )
        await _append_failed_execution_event(
            session,
            proposal=proposal,
            execution=execution,
            message=GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE,
            error_code="token_unavailable",
            actor_user_id=input_payload.requested_by_user_id,
        )
        await session.commit()
        raise GitHubIssueProviderExecutionError(
            GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE
        ) from exc

    execution.status = ACTION_EXECUTION_STATUS_RUNNING
    execution.started_at = datetime.now(timezone.utc)
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_STARTED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="GitHub issue execution started after the durable claim was committed.",
        confirmation_received=True,
        external_execution_enabled=True,
        reason=str(execution.id),
        actor_user_id=input_payload.requested_by_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "repository_full_name": issue_payload.repository_full_name,
        },
    )
    await session.commit()

    try:
        await _validate_evidence_for_live_execution(
            session,
            workspace_id=workspace_id,
            proposal=proposal,
        )
    except GitHubIssueExecutionConflictError as exc:
        await _mark_pre_provider_failed(
            session,
            proposal=proposal,
            execution=execution,
            message=exc.detail,
        )
        await _append_failed_execution_event(
            session,
            proposal=proposal,
            execution=execution,
            message=exc.detail,
            error_code="proposal_evidence_invalid",
            actor_user_id=input_payload.requested_by_user_id,
        )
        await session.commit()
        raise

    try:
        raw_response = await create_issue(
            access_token=access_token,
            repository_full_name=issue_payload.repository_full_name,
            title=issue_payload.title,
            body=_body_with_execution_marker(
                issue_payload.body,
                execution=execution,
            ),
            labels=issue_payload.labels,
            assignees=issue_payload.assignees,
        )
    except Exception as exc:
        await _mark_uncertain(
            session,
            proposal=proposal,
            execution=execution,
            actor_user_id=input_payload.requested_by_user_id,
        )
        await session.commit()
        raise GitHubIssueProviderExecutionError(
            GITHUB_ISSUE_EXECUTION_OUTCOME_UNCERTAIN
        ) from exc

    sanitized_response = sanitize_github_issue_response(raw_response)
    sanitized_response["idempotency_key"] = idempotency_key
    execution.status = ACTION_EXECUTION_STATUS_SUCCEEDED
    execution.provider_response = sanitized_response
    execution.external_id = _external_id_from_response(sanitized_response)
    execution.error_message = None
    execution.finished_at = datetime.now(timezone.utc)
    proposal.status = ACTION_PROPOSAL_STATUS_EXECUTED
    await session.flush()
    await session.refresh(proposal)
    await session.refresh(execution)
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_SUCCEEDED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="GitHub issue execution succeeded and provider receipt was recorded.",
        confirmation_received=True,
        external_execution_enabled=True,
        reason=str(execution.id),
        actor_user_id=input_payload.requested_by_user_id,
        external_result_id=_external_result_id_from_response(sanitized_response),
        external_result_url=_external_result_url_from_response(sanitized_response),
        event_metadata={
            "execution_id": str(execution.id),
            "issue_number": sanitized_response.get("number"),
            "provider_state": sanitized_response.get("state"),
        },
    )
    await session.commit()
    return _execution_result(proposal=proposal, execution=execution)


def validate_github_issue_payload(payload: Mapping[str, Any]) -> GitHubIssuePayload:
    secret_key = _first_secret_like_key(payload)
    if secret_key is not None:
        raise GitHubIssueExecutionError(
            f"payload contains secret-like key: {secret_key}"
        )
    repository_full_name = _required_text(
        payload.get("repository_full_name"),
        "repository_full_name is required",
    )
    if not _looks_like_repository_full_name(repository_full_name):
        raise GitHubIssueExecutionError("repository_full_name must look like owner/repo")
    title = _required_text(payload.get("title"), "title is required")
    body = _optional_text(payload.get("body"))
    labels = _optional_string_list(payload.get("labels"), field_name="labels")
    assignees = _optional_string_list(payload.get("assignees"), field_name="assignees")
    return GitHubIssuePayload(
        repository_full_name=repository_full_name,
        title=title,
        body=body,
        labels=labels,
        assignees=assignees,
    )


def sanitize_github_issue_response(response: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "id",
        "node_id",
        "number",
        "state",
        "title",
        "html_url",
        "url",
    }
    sanitized: dict[str, Any] = {}
    for key in allowed_keys:
        value = response.get(key)
        if isinstance(value, str):
            sanitized[key] = value[:1000]
        elif isinstance(value, bool | int | float) or value is None:
            sanitized[key] = value
    return sanitized


def _execution_result(
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "proposal": {
            "id": proposal.id,
            "status": proposal.status,
        },
        "execution": {
            "id": execution.id,
            "status": execution.status,
            "workspace_id": execution.workspace_id,
            "requested_by_user_id": execution.requested_by_user_id,
            "connection_id": execution.connection_id,
            "client_idempotency_key": execution.client_idempotency_key,
            "request_hash": execution.request_hash,
            "external_id": execution.external_id,
            "provider_response": execution.provider_response or {},
            "error_message": execution.error_message,
            "claimed_at": execution.claimed_at,
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "reconciled_at": execution.reconciled_at,
        },
        "is_live": True,
        "external_write_performed": execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED,
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "receipt": _execution_receipt(proposal=proposal, execution=execution),
        "warnings": warnings or [],
    }


async def _get_proposal_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    for_update: bool = False,
) -> ActionProposal:
    statement = (
        select(ActionProposal)
        .where(ActionProposal.workspace_id == workspace_id)
        .where(ActionProposal.id == proposal_id)
    )
    if for_update:
        statement = statement.with_for_update()
    proposal = await session.scalar(statement)
    if proposal is None:
        raise GitHubIssueExecutionNotFoundError(
            GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_FOUND
        )
    return proposal


def _validate_proposal_for_execution(proposal: ActionProposal) -> None:
    if proposal.status != ACTION_PROPOSAL_STATUS_APPROVED:
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_APPROVED
        )
    if (
        proposal.target_provider != ACTION_TARGET_PROVIDER_GITHUB
        or proposal.action_type != ACTION_TYPE_CREATE_GITHUB_ISSUE
    ):
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION)


async def _validate_evidence_for_live_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal: ActionProposal,
) -> None:
    if not proposal.evidence_refs:
        raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_EVIDENCE_REQUIRED)
    try:
        await validate_action_proposal_evidence(
            session,
            workspace_id=workspace_id,
            proposal=proposal,
        )
    except ActionProposalEvidenceValidationError as exc:
        raise GitHubIssueExecutionConflictError(exc.detail) from exc


def _validate_repository_allowlist(issue_payload: GitHubIssuePayload) -> None:
    allowed_repositories = _github_write_allowed_repositories()
    if not allowed_repositories:
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_ALLOWED_REPOS_REQUIRED
        )
    if _normalize_repository_full_name(
        issue_payload.repository_full_name
    ) not in allowed_repositories:
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_REPOSITORY_NOT_ALLOWED
        )


def _github_write_allowed_repositories() -> set[str]:
    raw_value = settings.github_write_allowed_repos
    if not raw_value:
        return set()

    repositories: set[str] = set()
    for chunk in raw_value.replace(";", ",").replace("\n", ",").split(","):
        for item in chunk.split():
            normalized = _normalize_repository_full_name(item)
            if _looks_like_repository_full_name(normalized):
                repositories.add(normalized)
    return repositories


def _normalize_repository_full_name(value: str) -> str:
    return value.strip().casefold()


async def _get_connection_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await session.scalar(
        select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
    )
    if connection is None or connection.workspace_id != workspace_id:
        raise GitHubIssueExecutionNotFoundError(GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_FOUND)
    if connection.provider != INTEGRATION_PROVIDER_GITHUB:
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_GITHUB)
    if connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_CONNECTION_NOT_CONNECTED
        )
    if not connection.encrypted_access_token:
        raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_TOKEN_MISSING)
    return connection


async def _get_execution_by_idempotency_key(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    idempotency_key: str,
) -> ActionExecution | None:
    return await session.scalar(
        select(ActionExecution)
        .where(ActionExecution.workspace_id == workspace_id)
        .where(ActionExecution.client_idempotency_key == idempotency_key)
        .order_by(ActionExecution.created_at.asc(), ActionExecution.id.asc())
    )


async def _get_active_or_successful_execution(
    session: AsyncSession,
    *,
    proposal_id: UUID,
) -> ActionExecution | None:
    return await session.scalar(
        select(ActionExecution)
        .where(ActionExecution.action_proposal_id == proposal_id)
        .where(
            ActionExecution.status.in_(
                (
                    ACTION_EXECUTION_STATUS_CLAIMED,
                    ACTION_EXECUTION_STATUS_RUNNING,
                    ACTION_EXECUTION_STATUS_SUCCEEDED,
                    ACTION_EXECUTION_STATUS_UNCERTAIN,
                )
            )
        )
        .order_by(ActionExecution.created_at.asc(), ActionExecution.id.asc())
    )


async def _resolve_existing_execution(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    request_hash: str | None,
    actor_user_id: UUID,
) -> dict[str, Any]:
    if (
        execution.action_proposal_id != proposal.id
        or (request_hash is not None and execution.request_hash != request_hash)
    ):
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_IDEMPOTENCY_REUSED
        )

    if execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED:
        await _append_execution_audit_event(
            session,
            proposal=proposal,
            event_type=ACTION_EXECUTION_EVENT_DUPLICATE_RETURNED_EXISTING_RECEIPT,
            status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
            message=GITHUB_ISSUE_EXECUTION_DUPLICATE_RECEIPT,
            confirmation_received=True,
            external_execution_enabled=True,
            reason=f"{execution.id}:{actor_user_id}:duplicate_successful_receipt",
            actor_user_id=actor_user_id,
            external_result_id=_external_result_id_from_response(
                execution.provider_response or {}
            ),
            external_result_url=_external_result_url_from_response(
                execution.provider_response or {}
            ),
            event_metadata={
                "execution_id": str(execution.id),
                "proposal_status": proposal.status,
            },
        )
        return _execution_result(
            proposal=proposal,
            execution=execution,
            warnings=[GITHUB_ISSUE_EXECUTION_DUPLICATE_RECEIPT],
        )

    if execution.status in {
        ACTION_EXECUTION_STATUS_CLAIMED,
        ACTION_EXECUTION_STATUS_RUNNING,
        ACTION_EXECUTION_STATUS_UNCERTAIN,
    }:
        raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_IN_PROGRESS)

    raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_RETRY_KEY_REQUIRED)


async def _mark_pre_provider_failed(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    message: str,
) -> None:
    execution.status = ACTION_EXECUTION_STATUS_FAILED
    execution.error_message = message
    execution.finished_at = datetime.now(timezone.utc)
    proposal.status = ACTION_PROPOSAL_STATUS_APPROVED
    await session.flush()
    await session.refresh(proposal)
    await session.refresh(execution)


async def _mark_uncertain(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    actor_user_id: UUID,
) -> None:
    execution.status = ACTION_EXECUTION_STATUS_UNCERTAIN
    execution.error_message = GITHUB_ISSUE_EXECUTION_OUTCOME_UNCERTAIN
    execution.finished_at = None
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_OUTCOME_UNCERTAIN,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=(
            "The provider request may have completed, but no authoritative "
            "receipt was recorded. Reconciliation is required."
        ),
        confirmation_received=True,
        external_execution_enabled=True,
        reason=str(execution.id),
        actor_user_id=actor_user_id,
        error_code="provider_outcome_uncertain",
        error_message=GITHUB_ISSUE_EXECUTION_OUTCOME_UNCERTAIN,
        event_metadata={
            "execution_id": str(execution.id),
            "request_hash": execution.request_hash,
        },
    )
    await session.flush()


def _required_idempotency_key(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None or len(normalized) < 8:
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_IDEMPOTENCY_REQUIRED)
    return normalized[:255]


def _execution_request_hash(
    *,
    proposal: ActionProposal,
    workspace_id: UUID,
    connection_id: UUID,
    requested_by_user_id: UUID,
) -> str:
    material = {
        "workspace_id": str(workspace_id),
        "proposal_id": str(proposal.id),
        "proposal_updated_at": proposal.updated_at.isoformat(),
        "target_provider": proposal.target_provider,
        "action_type": proposal.action_type,
        "payload": proposal.payload or {},
        "evidence_refs": proposal.evidence_refs or [],
        "connection_id": str(connection_id),
        "requested_by_user_id": str(requested_by_user_id),
    }
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def execution_request_marker(execution: ActionExecution) -> str:
    return f"<!-- founderos-execution:{execution.id}:{execution.request_hash} -->"


def _validate_body_marker_capacity(body: str | None) -> None:
    placeholder_marker = (
        "<!-- founderos-execution:"
        "00000000-0000-0000-0000-000000000000:"
        f"{'0' * 64} -->"
    )
    separator = "\n\n" if body else ""
    combined = f"{body or ''}{separator}{placeholder_marker}"
    if len(combined.encode("utf-8")) > GITHUB_ISSUE_BODY_MAX_BYTES:
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_BODY_TOO_LARGE)


def _body_with_execution_marker(
    body: str | None,
    *,
    execution: ActionExecution,
) -> str:
    marker = execution_request_marker(execution)
    return f"{body}\n\n{marker}" if body else marker


def _required_text(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GitHubIssueExecutionError(message)
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GitHubIssueExecutionError(f"{field_name} must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise GitHubIssueExecutionError(f"{field_name} must be a list of strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped[:120])
    return normalized


def _looks_like_repository_full_name(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 2 and all(part.strip() for part in parts)


def _first_secret_like_key(payload: Mapping[str, Any]) -> str | None:
    for key, value in payload.items():
        key_text = str(key).strip().casefold()
        if key_text in SECRET_LIKE_KEYS:
            return key_text
        if isinstance(value, Mapping):
            nested = _first_secret_like_key(value)
            if nested is not None:
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping):
                    nested = _first_secret_like_key(item)
                    if nested is not None:
                        return nested
    return None


def _external_id_from_response(response: Mapping[str, Any]) -> str | None:
    for key in ("html_url", "id", "number", "url"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
        if isinstance(value, int):
            return str(value)
    return None


def _external_result_id_from_response(response: Mapping[str, Any]) -> str | None:
    for key in ("number", "id", "node_id"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
        if isinstance(value, int):
            return str(value)
    return None


def _external_result_url_from_response(response: Mapping[str, Any]) -> str | None:
    for key in ("html_url", "url"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:1000]
    external_id = response.get("external_id")
    if isinstance(external_id, str) and external_id.startswith("https://"):
        return external_id[:1000]
    return None


def _execution_receipt(
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
) -> dict[str, Any]:
    provider_response = execution.provider_response or {}
    return {
        "provider": proposal.target_provider,
        "action": proposal.action_type,
        "status": execution.status,
        "external_execution_enabled": True,
        "confirmation_received": True,
        "external_result_id": _external_result_id_from_response(provider_response),
        "external_result_url": _external_result_url_from_response(provider_response),
        "external_write_performed": execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED,
        "provider_result": (
            "succeeded"
            if execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED
            else (
                "uncertain"
                if execution.status == ACTION_EXECUTION_STATUS_UNCERTAIN
                else "failed"
            )
        ),
        "error_code": (
            "provider_execution_failed"
            if execution.status == ACTION_EXECUTION_STATUS_FAILED
            else (
                "provider_outcome_uncertain"
                if execution.status == ACTION_EXECUTION_STATUS_UNCERTAIN
                else None
            )
        ),
        "error_message": execution.error_message,
        "idempotency_key": execution.client_idempotency_key,
        "created_at": execution.created_at,
        "updated_at": execution.updated_at,
    }


async def _append_blocked_execution_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    detail: str,
    confirmation_received: bool,
    actor_user_id: UUID,
) -> None:
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=(
            ACTION_EXECUTION_EVENT_REPOSITORY_NOT_ALLOWED
            if detail
            in {
                GITHUB_ISSUE_EXECUTION_ALLOWED_REPOS_REQUIRED,
                GITHUB_ISSUE_EXECUTION_REPOSITORY_NOT_ALLOWED,
            }
            else ACTION_EXECUTION_EVENT_BLOCKED
        ),
        status=(
            ACTION_EXECUTION_EVENT_STATUS_UNSUPPORTED
            if detail == GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION
            else ACTION_EXECUTION_EVENT_STATUS_BLOCKED
        ),
        message=f"Execution blocked: {detail}. No external write occurred.",
        confirmation_received=confirmation_received,
        external_execution_enabled=True,
        reason=_error_code_from_detail(detail),
        actor_user_id=actor_user_id,
        error_code=_error_code_from_detail(detail),
        error_message=detail,
        event_metadata={
            "proposal_status": proposal.status,
            **_repository_metadata(proposal),
        },
    )


async def _append_failed_execution_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    message: str,
    error_code: str,
    actor_user_id: UUID,
) -> None:
    await _append_execution_audit_event(
        session,
        proposal=proposal,
        event_type=ACTION_EXECUTION_EVENT_FAILED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=f"GitHub issue execution failed: {message}.",
        confirmation_received=True,
        external_execution_enabled=True,
        reason=str(execution.id),
        actor_user_id=actor_user_id,
        error_code=error_code,
        error_message=message,
        event_metadata={"execution_id": str(execution.id)},
    )


async def _append_execution_audit_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    event_type: str,
    status: str,
    message: str,
    confirmation_received: bool,
    external_execution_enabled: bool,
    reason: str,
    actor_user_id: UUID,
    event_metadata: Mapping[str, Any] | None = None,
    external_result_id: str | None = None,
    external_result_url: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    await append_execution_event(
        session,
        workspace_id=proposal.workspace_id,
        action_proposal_id=proposal.id,
        event_type=event_type,
        actor=f"user:{actor_user_id}",
        status=status,
        message=message,
        idempotency_key=execution_event_idempotency_key(
            workspace_id=proposal.workspace_id,
            action_proposal_id=proposal.id,
            event_type=event_type,
            external_execution_enabled=external_execution_enabled,
            confirmation_received=confirmation_received,
            reason=reason,
        ),
        provider=proposal.target_provider,
        action=proposal.action_type,
        external_execution_enabled=external_execution_enabled,
        confirmation_received=confirmation_received,
        event_metadata=event_metadata or {},
        external_result_id=external_result_id,
        external_result_url=external_result_url,
        error_code=error_code,
        error_message=error_message,
    )


def _error_code_from_detail(detail: str) -> str:
    normalized = detail.strip().casefold()
    safe = "".join(char if char.isalnum() else "_" for char in normalized)
    return "_".join(part for part in safe.split("_") if part)[:120] or "blocked"


def _repository_metadata(proposal: ActionProposal) -> dict[str, str]:
    repository_full_name = proposal.payload.get("repository_full_name")
    if not isinstance(repository_full_name, str) or not repository_full_name.strip():
        return {}
    return {"repository_full_name": repository_full_name.strip()[:255]}
