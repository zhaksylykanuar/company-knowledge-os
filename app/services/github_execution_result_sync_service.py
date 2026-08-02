from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.action_models import (
    ACTION_EXECUTION_EVENT_OUTCOME_RECONCILED,
    ACTION_EXECUTION_EVENT_RECONCILIATION_PENDING,
    ACTION_EXECUTION_EVENT_RESULT_SYNC_FAILED,
    ACTION_EXECUTION_EVENT_RESULT_SYNC_STARTED,
    ACTION_EXECUTION_EVENT_RESULT_SYNCED,
    ACTION_EXECUTION_EVENT_STATUS_BLOCKED,
    ACTION_EXECUTION_EVENT_STATUS_RECORDED,
    ACTION_EXECUTION_EVENT_WRITE_NOT_OBSERVED,
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
from app.db.canonical_models import SOURCE_RECORD_PROVIDER_GITHUB, SourceRecord, Task
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)
from app.services.action_execution_audit_service import (
    append_execution_event,
    execution_event_idempotency_key,
    list_execution_events,
    serialize_execution_event,
)
from app.services.github_issue_client import GitHubIssueClientError, get_issue, list_issues
from app.services.github_issue_execution_service import (
    GitHubIssueExecutionError,
    GitHubIssuePayload,
    execution_request_marker,
    sanitize_github_issue_response,
    validate_github_issue_payload,
)
from app.services.github_normalization_service import (
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.real_connector_guard import require_real_connectors_enabled
from app.services.secret_encryption import SecretEncryptionError, decrypt_secret

GITHUB_EXECUTION_RESULT_SYNC_PROPOSAL_NOT_FOUND = "action proposal not found"
GITHUB_EXECUTION_RESULT_SYNC_NOT_EXECUTED = "action proposal is not executed"
GITHUB_EXECUTION_RESULT_SYNC_UNSUPPORTED_ACTION = "unsupported action proposal"
GITHUB_EXECUTION_RESULT_SYNC_RECEIPT_REQUIRED = (
    "successful execution receipt is required"
)
GITHUB_EXECUTION_RESULT_SYNC_ISSUE_NUMBER_REQUIRED = (
    "successful execution receipt does not include an issue number"
)
GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_NOT_FOUND = "github connection not found"
GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_AMBIGUOUS = (
    "multiple connected GitHub connections found; connection_id is required"
)
GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_NOT_CONNECTED = (
    "github connection is not connected"
)
GITHUB_EXECUTION_RESULT_SYNC_TOKEN_MISSING = (
    "github connection has no encrypted access token"
)
GITHUB_EXECUTION_RESULT_SYNC_TOKEN_UNAVAILABLE = "github token could not be decrypted"
GITHUB_EXECUTION_RESULT_SYNC_PROVIDER_READ_FAILED = "github issue read failed"
GITHUB_EXECUTION_RESULT_SYNC_MARKER_AMBIGUOUS = (
    "multiple GitHub issues matched the execution marker"
)
GITHUB_EXECUTION_RESULT_SYNC_WRITE_NOT_OBSERVED = (
    "no GitHub issue matched the execution marker in a complete snapshot"
)
GITHUB_EXECUTION_RESULT_SYNC_ABSENCE_GRACE_PERIOD = timedelta(seconds=60)


class GitHubExecutionResultSyncError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GitHubExecutionResultSyncNotFoundError(GitHubExecutionResultSyncError):
    pass


class GitHubExecutionResultSyncConflictError(GitHubExecutionResultSyncError):
    pass


class GitHubExecutionResultSyncProviderReadError(GitHubExecutionResultSyncError):
    pass


@dataclass(frozen=True)
class GitHubExecutionResultSyncInput:
    requested_by_user_id: UUID
    connection_id: UUID | None = None


async def sync_github_issue_execution_result(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal_id: UUID,
    input_payload: GitHubExecutionResultSyncInput,
) -> dict[str, Any]:
    require_real_connectors_enabled()
    proposal = await _get_proposal_or_raise(
        session,
        workspace_id=workspace_id,
        proposal_id=proposal_id,
    )
    issue_payload = _validate_github_issue_proposal(proposal)
    execution = await _get_reconcilable_execution_or_raise(
        session,
        proposal=proposal,
        proposal_id=proposal.id,
    )
    requested_connection_id = input_payload.connection_id or execution.connection_id
    connection = await _get_connection_or_raise(
        session,
        workspace_id=workspace_id,
        connection_id=requested_connection_id,
    )
    issue_number = (
        _issue_number_from_receipt(execution.provider_response or {})
        if execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED
        else None
    )

    await _append_sync_event(
        session,
        proposal=proposal,
        execution=execution,
        event_type=ACTION_EXECUTION_EVENT_RESULT_SYNC_STARTED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="Post-execution GitHub issue result sync started. No external write occurred.",
        reason=f"{execution.id}:{issue_number or 'marker'}:started",
        issue_number=issue_number,
        actor_user_id=input_payload.requested_by_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "repository_full_name": issue_payload.repository_full_name,
            "issue_number": issue_number,
        },
    )

    try:
        access_token = decrypt_secret(connection.encrypted_access_token or "")
    except SecretEncryptionError as exc:
        await _append_sync_failure_event(
            session,
            proposal=proposal,
            execution=execution,
            issue_number=issue_number,
            issue_payload=issue_payload,
            detail=GITHUB_EXECUTION_RESULT_SYNC_TOKEN_UNAVAILABLE,
            error_code="token_unavailable",
            actor_user_id=input_payload.requested_by_user_id,
        )
        raise GitHubExecutionResultSyncConflictError(
            GITHUB_EXECUTION_RESULT_SYNC_TOKEN_UNAVAILABLE
        ) from exc

    snapshot_observed_at = datetime.now(timezone.utc)
    try:
        if execution.status == ACTION_EXECUTION_STATUS_SUCCEEDED:
            if issue_number is None:
                raise GitHubExecutionResultSyncConflictError(
                    GITHUB_EXECUTION_RESULT_SYNC_ISSUE_NUMBER_REQUIRED
                )
            raw_issue = await get_issue(
                access_token=access_token,
                repository_full_name=issue_payload.repository_full_name,
                issue_number=issue_number,
            )
        elif execution.status == ACTION_EXECUTION_STATUS_CLAIMED:
            return await _record_write_not_observed(
                session,
                workspace_id=workspace_id,
                proposal=proposal,
                execution=execution,
                issue_payload=issue_payload,
                actor_user_id=input_payload.requested_by_user_id,
                reason="provider_request_not_started",
            )
        else:
            candidates = await list_issues(
                access_token=access_token,
                repository_full_name=issue_payload.repository_full_name,
                state="all",
            )
            matches = _issues_matching_execution_marker(
                candidates,
                execution=execution,
            )
            if len(matches) > 1:
                raise GitHubExecutionResultSyncConflictError(
                    GITHUB_EXECUTION_RESULT_SYNC_MARKER_AMBIGUOUS
                )
            if not matches:
                retry_after = _absence_reconciliation_eligible_at(execution)
                if snapshot_observed_at < retry_after:
                    return await _record_reconciliation_pending(
                        session,
                        workspace_id=workspace_id,
                        proposal=proposal,
                        execution=execution,
                        issue_payload=issue_payload,
                        actor_user_id=input_payload.requested_by_user_id,
                        retry_after=retry_after,
                    )
                return await _record_write_not_observed(
                    session,
                    workspace_id=workspace_id,
                    proposal=proposal,
                    execution=execution,
                    issue_payload=issue_payload,
                    actor_user_id=input_payload.requested_by_user_id,
                    reason="complete_provider_snapshot",
                )
            raw_issue = matches[0]
            issue_number = _positive_int(raw_issue.get("number"))
            if issue_number is None:
                raise GitHubExecutionResultSyncProviderReadError(
                    GITHUB_EXECUTION_RESULT_SYNC_PROVIDER_READ_FAILED
                )
            _record_reconciled_success(
                proposal=proposal,
                execution=execution,
                raw_issue=raw_issue,
                reconciled_at=snapshot_observed_at,
            )
            await _append_sync_event(
                session,
                proposal=proposal,
                execution=execution,
                event_type=ACTION_EXECUTION_EVENT_OUTCOME_RECONCILED,
                status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
                message=(
                    "The uncertain GitHub write was matched by its exact "
                    "execution marker and recorded as succeeded."
                ),
                reason=f"{execution.id}:{issue_number}:reconciled",
                issue_number=issue_number,
                actor_user_id=input_payload.requested_by_user_id,
                external_result_id=str(issue_number),
                external_result_url=_safe_url(raw_issue.get("html_url")),
                event_metadata={
                    "execution_id": str(execution.id),
                    "repository_full_name": issue_payload.repository_full_name,
                    "issue_number": issue_number,
                    "request_hash": execution.request_hash,
                },
            )
    except GitHubIssueClientError as exc:
        await _append_sync_failure_event(
            session,
            proposal=proposal,
            execution=execution,
            issue_number=issue_number,
            issue_payload=issue_payload,
            detail=GITHUB_EXECUTION_RESULT_SYNC_PROVIDER_READ_FAILED,
            error_code="provider_read_failed",
            actor_user_id=input_payload.requested_by_user_id,
        )
        raise GitHubExecutionResultSyncProviderReadError(
            GITHUB_EXECUTION_RESULT_SYNC_PROVIDER_READ_FAILED
        ) from exc

    issue_record = _issue_record_from_github_response(
        raw_issue,
        repository_full_name=issue_payload.repository_full_name,
        fallback_number=issue_number,
    )
    sync_job = await _create_execution_result_sync_job(
        session,
        workspace_id=workspace_id,
        connection=connection,
        proposal=proposal,
        execution=execution,
        issue_record=issue_record,
    )
    normalization = await normalize_github_sync_job_local(
        session,
        workspace_id=workspace_id,
        sync_job_id=sync_job.id,
        options=GitHubNormalizationOptions(
            include_repositories=False,
            include_issues=True,
            include_pull_requests=False,
            persist_if_supported=True,
            snapshot_observed_at=snapshot_observed_at,
            provider_attested=True,
        ),
    )
    normalized_issue = _first_normalized_issue(normalization)
    canonical = await _canonical_issue_payload(
        session,
        workspace_id=workspace_id,
        normalized_issue=normalized_issue,
    )
    source_updated_at = _safe_text(issue_record.get("updated_at"))
    await _append_sync_event(
        session,
        proposal=proposal,
        execution=execution,
        event_type=ACTION_EXECUTION_EVENT_RESULT_SYNCED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message="Post-execution GitHub issue result synced into canonical records. No external write occurred.",
        reason=f"{execution.id}:{issue_number}:{source_updated_at}:synced",
        issue_number=issue_number,
        actor_user_id=input_payload.requested_by_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "sync_job_id": str(sync_job.id),
            "repository_full_name": issue_payload.repository_full_name,
            "issue_number": issue_number,
            "canonical_task_id": str(canonical["task_id"])
            if canonical.get("task_id")
            else None,
            "source_record_id": str(canonical["source_record_id"])
            if canonical.get("source_record_id")
            else None,
            "source_updated_at": source_updated_at,
        },
    )
    events = await list_execution_events(
        session,
        workspace_id=workspace_id,
        action_proposal_id=proposal.id,
    )
    return {
        "workspace_id": workspace_id,
        "proposal_id": proposal.id,
        "synced": True,
        "status": "synced",
        "provider": ACTION_TARGET_PROVIDER_GITHUB,
        "action": ACTION_TYPE_CREATE_GITHUB_ISSUE,
        "repository": issue_payload.repository_full_name,
        "issue": {
            "number": issue_number,
            "state": _safe_text(issue_record.get("state")),
            "title": _safe_text(issue_record.get("title")),
        },
        "sync_job": {
            "id": sync_job.id,
            "status": normalization["sync_job"]["status"],
            "records_seen": normalization["sync_job"]["records_seen"],
            "records_created": normalization["sync_job"]["records_created"],
            "records_updated": normalization["sync_job"]["records_updated"],
        },
        "canonical": canonical,
        "counts": normalization.get("counts") or {},
        "audit": [serialize_execution_event(event) for event in events],
        "warnings": [
            "Post-execution sync used read-only GitHub issue access.",
            "No external write occurred during sync.",
            *list(normalization.get("warnings") or []),
        ],
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
        raise GitHubExecutionResultSyncNotFoundError(
            GITHUB_EXECUTION_RESULT_SYNC_PROPOSAL_NOT_FOUND
        )
    return proposal


def _validate_github_issue_proposal(
    proposal: ActionProposal,
) -> GitHubIssuePayload:
    if (
        proposal.target_provider != ACTION_TARGET_PROVIDER_GITHUB
        or proposal.action_type != ACTION_TYPE_CREATE_GITHUB_ISSUE
    ):
        raise GitHubExecutionResultSyncError(
            GITHUB_EXECUTION_RESULT_SYNC_UNSUPPORTED_ACTION
        )
    try:
        return validate_github_issue_payload(proposal.payload or {})
    except GitHubIssueExecutionError as exc:
        raise GitHubExecutionResultSyncError(exc.detail) from exc


async def _get_reconcilable_execution_or_raise(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    proposal_id: UUID,
) -> ActionExecution:
    execution = await session.scalar(
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
    if execution is None:
        if proposal.status != ACTION_PROPOSAL_STATUS_EXECUTED:
            raise GitHubExecutionResultSyncConflictError(
                GITHUB_EXECUTION_RESULT_SYNC_NOT_EXECUTED
            )
        raise GitHubExecutionResultSyncConflictError(
            GITHUB_EXECUTION_RESULT_SYNC_RECEIPT_REQUIRED
        )
    return execution


async def _get_connection_or_raise(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID | None,
) -> IntegrationConnection:
    if connection_id is not None:
        connection = await session.scalar(
            select(IntegrationConnection)
            .where(IntegrationConnection.workspace_id == workspace_id)
            .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
            .where(IntegrationConnection.id == connection_id)
        )
        if connection is None:
            raise GitHubExecutionResultSyncNotFoundError(
                GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_NOT_FOUND
            )
        return _validate_connection(connection)

    rows = list(
        (
            await session.execute(
                select(IntegrationConnection)
                .where(IntegrationConnection.workspace_id == workspace_id)
                .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
                .where(IntegrationConnection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED)
                .order_by(IntegrationConnection.created_at.asc(), IntegrationConnection.id.asc())
            )
        ).scalars()
    )
    if not rows:
        raise GitHubExecutionResultSyncNotFoundError(
            GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_NOT_FOUND
        )
    if len(rows) > 1:
        raise GitHubExecutionResultSyncConflictError(
            GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_AMBIGUOUS
        )
    return _validate_connection(rows[0])


def _validate_connection(connection: IntegrationConnection) -> IntegrationConnection:
    if connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        raise GitHubExecutionResultSyncConflictError(
            GITHUB_EXECUTION_RESULT_SYNC_CONNECTION_NOT_CONNECTED
        )
    if not connection.encrypted_access_token:
        raise GitHubExecutionResultSyncConflictError(
            GITHUB_EXECUTION_RESULT_SYNC_TOKEN_MISSING
        )
    return connection


def _issue_number_from_receipt(provider_response: Mapping[str, Any]) -> int | None:
    value = provider_response.get("number")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    for key in ("html_url", "url", "external_id"):
        parsed = _issue_number_from_url(provider_response.get(key))
        if parsed is not None:
            return parsed
    return None


def _issue_number_from_url(value: Any) -> int | None:
    text = _safe_text(value)
    if not text:
        return None
    marker = "/issues/"
    if marker not in text:
        return None
    tail = text.rsplit(marker, 1)[-1].split("?", 1)[0].split("#", 1)[0]
    return int(tail) if tail.isdigit() else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _issues_matching_execution_marker(
    candidates: list[dict[str, Any]],
    *,
    execution: ActionExecution,
) -> list[dict[str, Any]]:
    marker = execution_request_marker(execution)
    return [
        candidate
        for candidate in candidates
        if candidate.get("pull_request") is None
        and isinstance(candidate.get("body"), str)
        and marker in candidate["body"]
    ]


def _record_reconciled_success(
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    raw_issue: Mapping[str, Any],
    reconciled_at: datetime,
) -> None:
    sanitized = sanitize_github_issue_response(raw_issue)
    sanitized["idempotency_key"] = execution.client_idempotency_key
    execution.status = ACTION_EXECUTION_STATUS_SUCCEEDED
    execution.provider_response = sanitized
    execution.external_id = _execution_external_id(sanitized)
    execution.error_message = None
    execution.finished_at = reconciled_at
    execution.reconciled_at = reconciled_at
    proposal.status = ACTION_PROPOSAL_STATUS_EXECUTED


def _absence_reconciliation_eligible_at(execution: ActionExecution) -> datetime:
    provider_start_boundary = execution.started_at or execution.claimed_at
    return provider_start_boundary + GITHUB_EXECUTION_RESULT_SYNC_ABSENCE_GRACE_PERIOD


async def _record_reconciliation_pending(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal: ActionProposal,
    execution: ActionExecution,
    issue_payload: GitHubIssuePayload,
    actor_user_id: UUID,
    retry_after: datetime,
) -> dict[str, Any]:
    await _append_sync_event(
        session,
        proposal=proposal,
        execution=execution,
        event_type=ACTION_EXECUTION_EVENT_RECONCILIATION_PENDING,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=(
            "No exact execution marker is visible yet, but the provider "
            "consistency grace period has not elapsed. The write remains uncertain."
        ),
        reason=f"{execution.id}:absence_grace_period",
        issue_number=None,
        actor_user_id=actor_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "repository_full_name": issue_payload.repository_full_name,
            "request_hash": execution.request_hash,
            "retry_after": retry_after.isoformat(),
        },
    )
    events = await list_execution_events(
        session,
        workspace_id=workspace_id,
        action_proposal_id=proposal.id,
    )
    return {
        "workspace_id": workspace_id,
        "proposal_id": proposal.id,
        "synced": False,
        "status": "reconciliation_pending",
        "provider": ACTION_TARGET_PROVIDER_GITHUB,
        "action": ACTION_TYPE_CREATE_GITHUB_ISSUE,
        "repository": issue_payload.repository_full_name,
        "issue": {
            "number": None,
            "state": None,
            "title": None,
        },
        "sync_job": None,
        "canonical": {
            "task_id": None,
            "source_record_id": None,
            "external_id": None,
            "evidence_refs_count": 0,
        },
        "counts": {},
        "audit": [serialize_execution_event(event) for event in events],
        "retry_after": retry_after,
        "warnings": [
            "The provider may still be converging after the write attempt.",
            f"Retry read-only reconciliation after {retry_after.isoformat()}.",
            "Do not retry the external write while reconciliation is pending.",
        ],
    }


async def _record_write_not_observed(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal: ActionProposal,
    execution: ActionExecution,
    issue_payload: GitHubIssuePayload,
    actor_user_id: UUID,
    reason: str,
) -> dict[str, Any]:
    reconciled_at = datetime.now(timezone.utc)
    provider_request_not_started = reason == "provider_request_not_started"
    execution.status = ACTION_EXECUTION_STATUS_FAILED
    execution.error_message = (
        "provider request did not start after the durable execution claim"
        if provider_request_not_started
        else GITHUB_EXECUTION_RESULT_SYNC_WRITE_NOT_OBSERVED
    )
    execution.finished_at = reconciled_at
    execution.reconciled_at = reconciled_at
    proposal.status = ACTION_PROPOSAL_STATUS_APPROVED
    await _append_sync_event(
        session,
        proposal=proposal,
        execution=execution,
        event_type=ACTION_EXECUTION_EVENT_WRITE_NOT_OBSERVED,
        status=ACTION_EXECUTION_EVENT_STATUS_RECORDED,
        message=(
            "The durable claim was recorded, but the provider request did not "
            "start. A retry must use a new idempotency key."
            if provider_request_not_started
            else (
                "A complete provider check found no GitHub issue with the exact "
                "execution marker. A later retry must use a new idempotency key."
            )
        ),
        reason=f"{execution.id}:{reason}:not_observed",
        issue_number=None,
        actor_user_id=actor_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "repository_full_name": issue_payload.repository_full_name,
            "request_hash": execution.request_hash,
            "reconciliation_basis": reason,
        },
        error_code="provider_write_not_observed",
        error_message=execution.error_message,
    )
    events = await list_execution_events(
        session,
        workspace_id=workspace_id,
        action_proposal_id=proposal.id,
    )
    return {
        "workspace_id": workspace_id,
        "proposal_id": proposal.id,
        "synced": False,
        "status": "write_not_observed",
        "provider": ACTION_TARGET_PROVIDER_GITHUB,
        "action": ACTION_TYPE_CREATE_GITHUB_ISSUE,
        "repository": issue_payload.repository_full_name,
        "issue": {
            "number": None,
            "state": None,
            "title": None,
        },
        "sync_job": None,
        "canonical": {
            "task_id": None,
            "source_record_id": None,
            "external_id": None,
            "evidence_refs_count": 0,
        },
        "counts": {},
        "audit": [serialize_execution_event(event) for event in events],
        "warnings": [
            (
                "The durable claim shows that the provider request did not start."
                if provider_request_not_started
                else "The complete provider read found no matching execution marker."
            ),
            "No external write occurred during reconciliation.",
            "A retry requires a new idempotency key.",
        ],
    }


def _execution_external_id(response: Mapping[str, Any]) -> str | None:
    for key in ("html_url", "id", "number", "url"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
        if isinstance(value, int):
            return str(value)
    return None


async def _create_execution_result_sync_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection: IntegrationConnection,
    proposal: ActionProposal,
    execution: ActionExecution,
    issue_record: dict[str, Any],
) -> SyncJob:
    sync_job = SyncJob(
        workspace_id=workspace_id,
        connection_id=connection.id,
        provider=INTEGRATION_PROVIDER_GITHUB,
        status=SYNC_JOB_STATUS_QUEUED,
        sync_type=SYNC_JOB_TYPE_MANUAL,
        cursor_before={
            "local_github": {
                "issues": [issue_record],
                "pull_requests": [],
            },
            "post_execution_sync": {
                "action": ACTION_TYPE_CREATE_GITHUB_ISSUE,
                "execution_id": str(execution.id),
                "proposal_id": str(proposal.id),
                "source": "github_issue_read_api",
            },
        },
        logs=[
            {
                "requested_by": "post_execution_sync",
                "execution_started": False,
                "note": "read-only sync of executed GitHub issue result",
            }
        ],
    )
    session.add(sync_job)
    await session.flush()
    await session.refresh(sync_job)
    return sync_job


def _issue_record_from_github_response(
    response: Mapping[str, Any],
    *,
    repository_full_name: str,
    fallback_number: int,
) -> dict[str, Any]:
    number = response.get("number")
    if not isinstance(number, int) or number <= 0:
        number = fallback_number
    if response.get("pull_request") is not None:
        raise GitHubExecutionResultSyncConflictError(
            "github issue read returned a pull request"
        )
    return {
        "id": _safe_text(response.get("id")) or f"{repository_full_name}#issue/{number}",
        "number": number,
        "title": _safe_text(response.get("title")) or f"GitHub issue {number}",
        "state": _safe_text(response.get("state")) or "open",
        "source_url": _safe_url(response.get("html_url")),
        "url": _safe_url(response.get("url")),
        "repository_full_name": repository_full_name,
        "created_at": _safe_text(response.get("created_at")),
        "updated_at": _safe_text(response.get("updated_at")),
        "metadata": {
            "source": "post_execution_sync",
            "synced_from_execution_result": True,
        },
    }


def _first_normalized_issue(normalization: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = normalization.get("normalized")
    if not isinstance(normalized, Mapping):
        return {}
    issues = normalized.get("issues")
    if isinstance(issues, list) and issues and isinstance(issues[0], Mapping):
        return issues[0]
    return {}


async def _canonical_issue_payload(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    normalized_issue: Mapping[str, Any],
) -> dict[str, Any]:
    external_id = _safe_text(normalized_issue.get("external_id"))
    task = None
    source_record = None
    if external_id:
        task = await session.scalar(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .where(Task.source_provider == SOURCE_RECORD_PROVIDER_GITHUB)
            .where(Task.external_id == external_id)
        )
        source_record = await session.scalar(
            select(SourceRecord)
            .where(SourceRecord.workspace_id == workspace_id)
            .where(SourceRecord.provider == SOURCE_RECORD_PROVIDER_GITHUB)
            .where(SourceRecord.external_id == external_id)
        )
    evidence_refs = normalized_issue.get("evidence_refs")
    return {
        "task_id": task.id if task is not None else None,
        "source_record_id": source_record.id if source_record is not None else None,
        "external_id": external_id,
        "evidence_refs_count": len(evidence_refs) if isinstance(evidence_refs, list) else 0,
    }


async def _append_sync_failure_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    issue_number: int | None,
    issue_payload: GitHubIssuePayload,
    detail: str,
    error_code: str,
    actor_user_id: UUID,
) -> None:
    await _append_sync_event(
        session,
        proposal=proposal,
        execution=execution,
        event_type=ACTION_EXECUTION_EVENT_RESULT_SYNC_FAILED,
        status=ACTION_EXECUTION_EVENT_STATUS_BLOCKED,
        message=f"Post-execution GitHub issue result sync failed: {detail}. No external write occurred.",
        reason=f"{execution.id}:{issue_number}:{error_code}",
        issue_number=issue_number,
        actor_user_id=actor_user_id,
        event_metadata={
            "execution_id": str(execution.id),
            "repository_full_name": issue_payload.repository_full_name,
            "issue_number": issue_number,
        },
        error_code=error_code,
        error_message=detail,
    )


async def _append_sync_event(
    session: AsyncSession,
    *,
    proposal: ActionProposal,
    execution: ActionExecution,
    event_type: str,
    status: str,
    message: str,
    reason: str,
    issue_number: int | None,
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
            external_execution_enabled=False,
            confirmation_received=True,
            reason=reason,
        ),
        provider=proposal.target_provider,
        action=proposal.action_type,
        external_execution_enabled=False,
        confirmation_received=True,
        event_metadata=event_metadata or {},
        external_result_id=external_result_id,
        external_result_url=external_result_url,
        error_code=error_code,
        error_message=error_message,
    )


def _safe_text(value: Any) -> str | None:
    if isinstance(value, int):
        return str(value)
    return value.strip()[:1000] if isinstance(value, str) and value.strip() else None


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and text.startswith(("http://", "https://")) and "@" not in text:
        return text
    return None
