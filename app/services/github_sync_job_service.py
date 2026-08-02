from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_CANCELLED,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_SUCCEEDED,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)

GITHUB_SYNC_JOB_NO_EXECUTION_WARNING = (
    "SyncJob record was created, but no GitHub sync execution was started in this step."
)
GITHUB_SYNC_JOB_CONNECTION_NOT_FOUND = "github connection not found"
GITHUB_SYNC_JOB_CONNECTION_NOT_CONNECTED = "github connection must be connected"
GITHUB_SYNC_JOB_NOT_FOUND = "github sync job not found"
GITHUB_SYNC_JOB_ALREADY_FINISHED = "github sync job is already finished"


@dataclass(frozen=True)
class GitHubManualSyncJobInput:
    cursor_before: dict[str, Any] | None = None
    notes: str | None = None
    requested_by: str = "operator_api_key"


class GitHubSyncJobError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def create_manual_github_sync_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    payload: GitHubManualSyncJobInput,
) -> dict[str, Any]:
    connection = await _get_connected_github_connection(
        session,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    log_entry: dict[str, Any] = {
        "requested_by": payload.requested_by,
        "execution_started": False,
        "note": "manual sync job record only",
    }
    if payload.notes:
        log_entry["notes"] = payload.notes

    sync_job = SyncJob(
        workspace_id=workspace_id,
        connection_id=connection.id,
        provider=INTEGRATION_PROVIDER_GITHUB,
        status=SYNC_JOB_STATUS_QUEUED,
        sync_type=SYNC_JOB_TYPE_MANUAL,
        cursor_before=payload.cursor_before,
        cursor_after=None,
        records_seen=0,
        records_created=0,
        records_updated=0,
        logs=[log_entry],
    )
    session.add(sync_job)
    await session.flush()
    await session.refresh(sync_job)
    return serialize_github_sync_job(sync_job)


async def list_github_sync_jobs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SyncJob)
            .where(SyncJob.workspace_id == workspace_id)
            .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
            .order_by(SyncJob.created_at.desc(), SyncJob.id.desc())
        )
    ).scalars()
    return [serialize_github_sync_job(sync_job) for sync_job in rows]


async def get_github_sync_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    sync_job_id: UUID,
) -> dict[str, Any] | None:
    sync_job = await session.scalar(
        select(SyncJob)
        .where(SyncJob.workspace_id == workspace_id)
        .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(SyncJob.id == sync_job_id)
    )
    if sync_job is None:
        return None
    return serialize_github_sync_job(sync_job)


async def request_github_sync_job_cancellation(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    sync_job_id: UUID,
    requested_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    sync_job = await session.scalar(
        select(SyncJob)
        .where(SyncJob.workspace_id == workspace_id)
        .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(SyncJob.id == sync_job_id)
        .with_for_update()
    )
    if sync_job is None:
        raise GitHubSyncJobError(GITHUB_SYNC_JOB_NOT_FOUND)
    if sync_job.status in {
        SYNC_JOB_STATUS_SUCCEEDED,
        SYNC_JOB_STATUS_FAILED,
        SYNC_JOB_STATUS_PARTIAL,
        SYNC_JOB_STATUS_CANCELLED,
    }:
        raise GitHubSyncJobError(GITHUB_SYNC_JOB_ALREADY_FINISHED)

    requested_at = now or datetime.now(timezone.utc)
    sync_job.cancel_requested_at = requested_at
    sync_job.logs = [
        *(sync_job.logs or []),
        {
            "event": "cancellation_requested",
            "requested_by": requested_by,
            "at": requested_at.isoformat(),
        },
    ]
    sync_job.status = SYNC_JOB_STATUS_CANCELLED
    sync_job.finished_at = requested_at
    sync_job.lease_owner = None
    sync_job.lease_expires_at = None
    sync_job.error_message = None
    await session.flush()
    await session.refresh(sync_job)
    return serialize_github_sync_job(sync_job)


def serialize_github_sync_job(sync_job: SyncJob) -> dict[str, Any]:
    request = _live_sync_request(sync_job.cursor_before)
    progress = _progress(sync_job.cursor_after)
    execution_started = sync_job.attempt_count > 0
    warnings = (
        []
        if request is not None
        else [GITHUB_SYNC_JOB_NO_EXECUTION_WARNING]
    )
    return {
        "id": sync_job.id,
        "workspace_id": sync_job.workspace_id,
        "connection_id": sync_job.connection_id,
        "provider": sync_job.provider,
        "status": sync_job.status,
        "sync_type": sync_job.sync_type,
        "started_at": sync_job.started_at,
        "finished_at": sync_job.finished_at,
        "cursor_before": sync_job.cursor_before,
        "cursor_after": sync_job.cursor_after,
        "records_seen": sync_job.records_seen,
        "records_created": sync_job.records_created,
        "records_updated": sync_job.records_updated,
        "error_message": sync_job.error_message,
        "logs": _serialize_logs(sync_job.logs),
        "attempt_count": sync_job.attempt_count,
        "max_attempts": sync_job.max_attempts,
        "next_attempt_at": sync_job.next_attempt_at,
        "cancel_requested_at": sync_job.cancel_requested_at,
        "progress": progress,
        "created_at": sync_job.created_at,
        "updated_at": sync_job.updated_at,
        "is_live": request is not None and execution_started,
        "execution_started": execution_started,
        "warnings": warnings,
    }


async def _get_connected_github_connection(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> IntegrationConnection:
    connection = await session.scalar(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id)
        .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(IntegrationConnection.id == connection_id)
    )
    if connection is None:
        raise GitHubSyncJobError(GITHUB_SYNC_JOB_CONNECTION_NOT_FOUND)
    if connection.status != INTEGRATION_CONNECTION_STATUS_CONNECTED:
        raise GitHubSyncJobError(GITHUB_SYNC_JOB_CONNECTION_NOT_CONNECTED)
    return connection


def _serialize_logs(value: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"events": value}


def _live_sync_request(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    request = value.get("github_app_live_sync")
    return request if isinstance(request, dict) else None


def _progress(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    progress = value.get("github_app_live_sync_progress")
    return progress if isinstance(progress, dict) else None
