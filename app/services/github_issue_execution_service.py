from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_EXECUTION_STATUS_FAILED,
    ACTION_EXECUTION_STATUS_SUCCEEDED,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_PROPOSAL_STATUS_EXECUTED,
    ACTION_PROPOSAL_STATUS_FAILED,
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
from app.services.github_issue_client import GitHubIssueClientError, create_issue
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
    idempotency_key: str | None = None


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
    if input_payload.confirm_external_write is not True:
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_CONFIRM_REQUIRED)

    proposal = await _get_proposal_or_raise(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
    )
    _validate_proposal_for_execution(proposal)
    issue_payload = validate_github_issue_payload(proposal.payload or {})
    connection = await _get_connection_or_raise(
        session,
        workspace_id=workspace_id,
        connection_id=input_payload.connection_id,
    )
    await _ensure_no_successful_execution(session, proposal_id=proposal.id)

    started_at = datetime.now(timezone.utc)
    execution = ActionExecution(
        action_proposal_id=proposal.id,
        started_at=started_at,
        provider_response={
            "idempotency_key": _optional_text(input_payload.idempotency_key),
        }
        if _optional_text(input_payload.idempotency_key)
        else {},
    )
    session.add(execution)
    await session.flush()

    try:
        access_token = decrypt_secret(connection.encrypted_access_token or "")
    except SecretEncryptionError as exc:
        await _mark_failed(
            session,
            proposal=proposal,
            execution=execution,
            message=GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE,
        )
        raise GitHubIssueProviderExecutionError(
            GITHUB_ISSUE_EXECUTION_TOKEN_UNAVAILABLE
        ) from exc

    try:
        raw_response = await create_issue(
            access_token=access_token,
            repository_full_name=issue_payload.repository_full_name,
            title=issue_payload.title,
            body=issue_payload.body,
            labels=issue_payload.labels,
            assignees=issue_payload.assignees,
        )
    except GitHubIssueClientError as exc:
        message = _sanitize_error_message(exc.detail, access_token=access_token)
        await _mark_failed(
            session,
            proposal=proposal,
            execution=execution,
            message=message,
        )
        raise GitHubIssueProviderExecutionError(message) from exc

    sanitized_response = sanitize_github_issue_response(raw_response)
    execution.status = ACTION_EXECUTION_STATUS_SUCCEEDED
    execution.provider_response = sanitized_response
    execution.external_id = _external_id_from_response(sanitized_response)
    execution.finished_at = datetime.now(timezone.utc)
    proposal.status = ACTION_PROPOSAL_STATUS_EXECUTED
    await session.flush()
    await session.refresh(proposal)
    await session.refresh(execution)
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
) -> dict[str, Any]:
    return {
        "proposal": {
            "id": proposal.id,
            "status": proposal.status,
        },
        "execution": {
            "id": execution.id,
            "status": execution.status,
            "external_id": execution.external_id,
            "provider_response": execution.provider_response or {},
            "error_message": execution.error_message,
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
        },
        "is_live": True,
        "external_write_performed": execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED,
        "provider": INTEGRATION_PROVIDER_GITHUB,
        "warnings": [],
    }


async def _get_proposal_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
) -> ActionProposal:
    proposal = await session.scalar(
        select(ActionProposal)
        .where(ActionProposal.workspace_id == workspace_id)
        .where(ActionProposal.id == proposal_id)
    )
    if proposal is None:
        raise GitHubIssueExecutionNotFoundError(
            GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_FOUND
        )
    return proposal


def _validate_proposal_for_execution(proposal: ActionProposal) -> None:
    if proposal.status == ACTION_PROPOSAL_STATUS_EXECUTED:
        raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_ALREADY_EXECUTED)
    if proposal.status != ACTION_PROPOSAL_STATUS_APPROVED:
        raise GitHubIssueExecutionConflictError(
            GITHUB_ISSUE_EXECUTION_PROPOSAL_NOT_APPROVED
        )
    if (
        proposal.target_provider != ACTION_TARGET_PROVIDER_GITHUB
        or proposal.action_type != ACTION_TYPE_CREATE_GITHUB_ISSUE
    ):
        raise GitHubIssueExecutionError(GITHUB_ISSUE_EXECUTION_UNSUPPORTED_ACTION)


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


async def _ensure_no_successful_execution(
    session: AsyncSession,
    *,
    proposal_id: UUID,
) -> None:
    existing = await session.scalar(
        select(ActionExecution)
        .where(ActionExecution.action_proposal_id == proposal_id)
        .where(ActionExecution.status == ACTION_EXECUTION_STATUS_SUCCEEDED)
    )
    if existing is not None:
        raise GitHubIssueExecutionConflictError(GITHUB_ISSUE_EXECUTION_ALREADY_EXECUTED)


async def _mark_failed(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    message: str,
) -> None:
    execution.status = ACTION_EXECUTION_STATUS_FAILED
    execution.error_message = message
    execution.finished_at = datetime.now(timezone.utc)
    proposal.status = ACTION_PROPOSAL_STATUS_FAILED
    await session.flush()
    await session.refresh(proposal)
    await session.refresh(execution)


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


def _sanitize_error_message(message: str, *, access_token: str) -> str:
    sanitized = message.replace(access_token, "[redacted]")
    lower = sanitized.casefold()
    if any(marker in lower for marker in SECRET_LIKE_KEYS):
        return "github issue creation failed"
    return sanitized[:500] or "github issue creation failed"


def _external_id_from_response(response: Mapping[str, Any]) -> str | None:
    for key in ("html_url", "id", "number", "url"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
        if isinstance(value, int):
            return str(value)
    return None
