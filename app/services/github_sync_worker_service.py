"""Durable, resumable GitHub provider-sync worker.

PostgreSQL owns queue state and leases. Provider I/O always runs after the
claim/authorization transaction is closed, and each repository is normalized
in its own short transaction.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.integration_models import (
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_CANCELLED,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_RUNNING,
    SYNC_JOB_STATUS_SUCCEEDED,
    IntegrationConnection,
    SyncJob,
)
from app.services.github_app_live_sync_service import (
    GitHubAppLiveSyncConflictError,
    GitHubAppLiveSyncError,
    GitHubAppLiveSyncInput,
    GitHubAppLiveSyncNotFoundError,
    GitHubAppLiveSyncPrepared,
    GitHubAppLiveSyncProviderReadError,
    GitHubRepositoryBatch,
    open_github_app_provider_context,
    prepare_github_app_live_sync,
    read_github_app_repository_batch,
)
from app.services.github_normalization_service import (
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.real_connector_guard import RealConnectorsDisabledError


_LOGGER = logging.getLogger("founderos.github_sync_worker")
_RETRYABLE_ERROR_CODE = "github_provider_read_failed"
_TERMINAL_ERROR_CODE = "github_sync_configuration_invalid"
_UNEXPECTED_ERROR_CODE = "github_sync_unexpected_failure"


class GitHubSyncWorkerLostLease(RuntimeError):
    pass


class GitHubSyncWorkerCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubSyncJobClaim:
    id: UUID
    workspace_id: UUID
    lease_owner: str
    input_payload: GitHubAppLiveSyncInput
    requested_by: str


async def claim_next_github_sync_job(
    session: AsyncSession,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> GitHubSyncJobClaim | None:
    claim_time = now or datetime.now(timezone.utc)
    await _expire_exhausted_leases(session, now=claim_time)
    eligible = or_(
        and_(
            SyncJob.status == SYNC_JOB_STATUS_QUEUED,
            SyncJob.next_attempt_at <= claim_time,
        ),
        and_(
            SyncJob.status == SYNC_JOB_STATUS_RUNNING,
            SyncJob.lease_expires_at.is_not(None),
            SyncJob.lease_expires_at <= claim_time,
        ),
    )
    sync_job = await session.scalar(
        select(SyncJob)
        .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(
            SyncJob.cursor_before["github_app_live_sync"].is_not(None)
        )
        .where(SyncJob.cancel_requested_at.is_(None))
        .where(SyncJob.attempt_count < SyncJob.max_attempts)
        .where(eligible)
        .order_by(SyncJob.next_attempt_at.asc(), SyncJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if sync_job is None:
        return None
    try:
        input_payload, requested_by = _parse_job_request(sync_job)
    except GitHubAppLiveSyncError:
        sync_job.status = SYNC_JOB_STATUS_FAILED
        sync_job.finished_at = claim_time
        sync_job.error_message = "github sync failed"
        sync_job.lease_owner = None
        sync_job.lease_expires_at = None
        sync_job.cursor_after = _with_progress_phase(
            sync_job.cursor_after,
            phase=SYNC_JOB_STATUS_FAILED,
            now=claim_time,
        )
        sync_job.logs = [
            *(sync_job.logs or []),
            {
                "event": SYNC_JOB_STATUS_FAILED,
                "error_code": _TERMINAL_ERROR_CODE,
                "at": claim_time.isoformat(),
            },
        ]
        await session.flush()
        return None
    lease_owner = f"{worker_id}:{uuid4().hex}"
    sync_job.status = SYNC_JOB_STATUS_RUNNING
    sync_job.started_at = sync_job.started_at or claim_time
    sync_job.finished_at = None
    sync_job.attempt_count += 1
    sync_job.lease_owner = lease_owner
    sync_job.lease_expires_at = claim_time + timedelta(
        seconds=settings.github_sync_job_lease_seconds
    )
    sync_job.error_message = None
    sync_job.cursor_after = _with_progress_phase(
        sync_job.cursor_after,
        phase="running",
        now=claim_time,
    )
    sync_job.logs = [
        *(sync_job.logs or []),
        {
            "event": "claimed",
            "attempt": sync_job.attempt_count,
            "at": claim_time.isoformat(),
        },
    ]
    await session.flush()
    return GitHubSyncJobClaim(
        id=sync_job.id,
        workspace_id=sync_job.workspace_id,
        lease_owner=lease_owner,
        input_payload=input_payload,
        requested_by=requested_by,
    )


async def process_one_github_sync_job(
    *,
    client: httpx.AsyncClient,
    worker_id: str,
) -> bool:
    async with AsyncSessionLocal() as session, session.begin():
        claim = await claim_next_github_sync_job(
            session,
            worker_id=worker_id,
        )
    if claim is None:
        return False

    try:
        prepared = await _prepare_claim(claim)
        await _renew_or_cancel(claim)
        provider = await open_github_app_provider_context(
            prepared,
            client=client,
        )
        completed = await _completed_repositories(claim)
        remaining = [
            repository
            for repository in prepared.repositories
            if repository.casefold() not in completed
        ]
        if not remaining:
            await _finish_resumed_job(claim)
            return True
        for repository in remaining:
            await _renew_or_cancel(claim)
            batch = await read_github_app_repository_batch(
                prepared,
                provider,
                repository_full_name=repository,
                client=client,
            )
            await _persist_repository_batch(
                claim,
                prepared=prepared,
                batch=batch,
            )
        return True
    except GitHubSyncWorkerCancelled:
        return True
    except GitHubSyncWorkerLostLease:
        return True
    except GitHubAppLiveSyncProviderReadError:
        await _retry_or_fail(
            claim,
            retryable=True,
            error_code=_RETRYABLE_ERROR_CODE,
        )
        return True
    except (
        GitHubAppLiveSyncConflictError,
        GitHubAppLiveSyncNotFoundError,
        RealConnectorsDisabledError,
        GitHubAppLiveSyncError,
    ):
        await _retry_or_fail(
            claim,
            retryable=False,
            error_code=_TERMINAL_ERROR_CODE,
        )
        return True
    except Exception:
        _LOGGER.error(
            "github_sync_worker_unexpected_failure",
            extra={"sync_job_id": str(claim.id)},
        )
        await _retry_or_fail(
            claim,
            retryable=True,
            error_code=_UNEXPECTED_ERROR_CODE,
        )
        return True


async def run_github_sync_workers(stop: asyncio.Event) -> None:
    """Run bounded workers over one shared HTTP connection pool."""

    limits = httpx.Limits(
        max_connections=max(4, settings.github_sync_worker_concurrency * 4),
        max_keepalive_connections=max(
            2,
            settings.github_sync_worker_concurrency * 2,
        ),
    )
    timeout = httpx.Timeout(settings.connector_network_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = [
            asyncio.create_task(
                _worker_loop(
                    stop,
                    client=client,
                    worker_id=f"worker-{index + 1}",
                ),
                name=f"founderos-github-sync-worker-{index + 1}",
            )
            for index in range(settings.github_sync_worker_concurrency)
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def _worker_loop(
    stop: asyncio.Event,
    *,
    client: httpx.AsyncClient,
    worker_id: str,
) -> None:
    while not stop.is_set():
        try:
            processed = await process_one_github_sync_job(
                client=client,
                worker_id=worker_id,
            )
        except Exception:
            _LOGGER.error("github_sync_worker_loop_failed")
            processed = False
        if processed:
            continue
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=settings.github_sync_worker_poll_seconds,
            )
        except TimeoutError:
            pass


async def _prepare_claim(
    claim: GitHubSyncJobClaim,
) -> GitHubAppLiveSyncPrepared:
    async with AsyncSessionLocal() as session:
        return await prepare_github_app_live_sync(
            session,
            workspace_id=claim.workspace_id,
            input_payload=claim.input_payload,
            requested_by=claim.requested_by,
        )


async def _renew_or_cancel(claim: GitHubSyncJobClaim) -> None:
    cancelled = False
    async with AsyncSessionLocal() as session, session.begin():
        sync_job = await _locked_claim_job(session, claim)
        if sync_job.cancel_requested_at is not None:
            _mark_cancelled(sync_job)
            cancelled = True
        else:
            sync_job.lease_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.github_sync_job_lease_seconds
            )
    if cancelled:
        raise GitHubSyncWorkerCancelled


async def _completed_repositories(
    claim: GitHubSyncJobClaim,
) -> set[str]:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(
            select(SyncJob)
            .where(SyncJob.id == claim.id)
            .where(SyncJob.workspace_id == claim.workspace_id)
        )
        if sync_job is None or sync_job.lease_owner != claim.lease_owner:
            raise GitHubSyncWorkerLostLease
        progress = _progress(sync_job.cursor_after)
        completed = progress.get("completed_repositories")
        if not isinstance(completed, list):
            return set()
        return {
            item.casefold()
            for item in completed
            if isinstance(item, str) and item.strip()
        }


async def _persist_repository_batch(
    claim: GitHubSyncJobClaim,
    *,
    prepared: GitHubAppLiveSyncPrepared,
    batch: GitHubRepositoryBatch,
) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        sync_job = await _locked_claim_job(session, claim)
        if sync_job.cancel_requested_at is not None:
            _mark_cancelled(sync_job)
            return
        request = _request_mapping(sync_job.cursor_before)
        progress_before = _progress(sync_job.cursor_after)
        completed_before = _string_list(
            progress_before.get("completed_repositories")
        )
        if batch.full_name.casefold() in {
            repository.casefold() for repository in completed_before
        }:
            return
        started_at = sync_job.started_at
        prior_status_partial = bool(progress_before.get("partial"))
        prior_counts = _counts(progress_before.get("counts"))
        prior_summaries = _summary_list(progress_before.get("repositories"))
        prior_created = sync_job.records_created
        prior_updated = sync_job.records_updated

        sync_job.status = SYNC_JOB_STATUS_QUEUED
        sync_job.cursor_before = {
            "github_app_live_sync": request,
            "local_github": {
                "repositories": [batch.repository],
                "issues": batch.issues,
                "pull_requests": batch.pull_requests,
            },
        }
        normalization = await normalize_github_sync_job_local(
            session,
            workspace_id=claim.workspace_id,
            sync_job_id=claim.id,
            options=GitHubNormalizationOptions(
                include_repositories=True,
                include_issues=prepared.include_issues,
                include_pull_requests=prepared.include_pull_requests,
                persist_if_supported=True,
                snapshot_observed_at=batch.observed_at,
                provider_attested=True,
                authoritative_issue_repositories=(
                    (batch.full_name,)
                    if prepared.include_issues
                    and _complete_issue_scope(prepared.issue_states)
                    else ()
                ),
                authoritative_pull_request_repositories=(
                    (batch.full_name,)
                    if prepared.include_pull_requests
                    and _complete_pull_request_scope(
                        prepared.pull_request_states
                    )
                    else ()
                ),
            ),
        )
        batch_status = str(normalization["sync_job"]["status"])
        counts = {
            "repositories": prior_counts["repositories"] + 1,
            "issues": prior_counts["issues"] + len(batch.issues),
            "pull_requests": (
                prior_counts["pull_requests"] + len(batch.pull_requests)
            ),
            "skipped_pull_requests": (
                prior_counts["skipped_pull_requests"]
                + batch.skipped_pull_requests
            ),
        }
        completed = [*completed_before, batch.full_name]
        summaries = [*prior_summaries, batch.summary]
        is_last = len(completed) >= len(prepared.repositories)
        partial = (
            prior_status_partial or batch_status == SYNC_JOB_STATUS_PARTIAL
        )
        now = datetime.now(timezone.utc)
        sync_job.cursor_before = {"github_app_live_sync": request}
        sync_job.cursor_after = {
            "github_app_live_sync_progress": {
                "phase": (
                    SYNC_JOB_STATUS_PARTIAL
                    if is_last and partial
                    else SYNC_JOB_STATUS_SUCCEEDED
                    if is_last
                    else SYNC_JOB_STATUS_RUNNING
                ),
                "completed_repositories": completed,
                "total_repositories": len(prepared.repositories),
                "repositories": summaries,
                "counts": counts,
                "partial": partial,
                "updated_at": now.isoformat(),
            }
        }
        sync_job.started_at = started_at
        sync_job.records_seen = (
            counts["repositories"] + counts["issues"] + counts["pull_requests"]
        )
        sync_job.records_created = (
            prior_created + int(normalization["sync_job"]["records_created"])
        )
        sync_job.records_updated = (
            prior_updated + int(normalization["sync_job"]["records_updated"])
        )
        sync_job.error_message = None
        if is_last:
            sync_job.status = (
                SYNC_JOB_STATUS_PARTIAL
                if partial
                else SYNC_JOB_STATUS_SUCCEEDED
            )
            sync_job.finished_at = now
            sync_job.lease_owner = None
            sync_job.lease_expires_at = None
            connection = await session.scalar(
                select(IntegrationConnection)
                .where(IntegrationConnection.id == sync_job.connection_id)
                .where(
                    IntegrationConnection.workspace_id
                    == sync_job.workspace_id
                )
            )
            if connection is not None:
                connection.last_sync_at = now
                connection.last_error = None
        else:
            sync_job.status = SYNC_JOB_STATUS_RUNNING
            sync_job.finished_at = None
            sync_job.lease_expires_at = now + timedelta(
                seconds=settings.github_sync_job_lease_seconds
            )
        sync_job.logs = [
            *(sync_job.logs or []),
            {
                "event": "repository_completed",
                "repository_index": len(completed),
                "repository_count": len(prepared.repositories),
                "counts": {
                    "issues": len(batch.issues),
                    "pull_requests": len(batch.pull_requests),
                },
                "at": now.isoformat(),
            },
        ]


async def _finish_resumed_job(claim: GitHubSyncJobClaim) -> None:
    cancelled = False
    async with AsyncSessionLocal() as session, session.begin():
        sync_job = await _locked_claim_job(session, claim)
        if sync_job.cancel_requested_at is not None:
            _mark_cancelled(sync_job)
            cancelled = True
        else:
            now = datetime.now(timezone.utc)
            progress = _progress(sync_job.cursor_after)
            partial = bool(progress.get("partial"))
            sync_job.status = (
                SYNC_JOB_STATUS_PARTIAL
                if partial
                else SYNC_JOB_STATUS_SUCCEEDED
            )
            sync_job.finished_at = now
            sync_job.lease_owner = None
            sync_job.lease_expires_at = None
            sync_job.cursor_after = _with_progress_phase(
                sync_job.cursor_after,
                phase=sync_job.status,
                now=now,
            )
    if cancelled:
        raise GitHubSyncWorkerCancelled


async def _retry_or_fail(
    claim: GitHubSyncJobClaim,
    *,
    retryable: bool,
    error_code: str,
) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        try:
            sync_job = await _locked_claim_job(session, claim)
        except GitHubSyncWorkerLostLease:
            return
        if sync_job.cancel_requested_at is not None:
            _mark_cancelled(sync_job)
            return
        now = datetime.now(timezone.utc)
        should_retry = retryable and sync_job.attempt_count < sync_job.max_attempts
        if should_retry:
            delay_seconds = min(
                300,
                settings.github_sync_job_retry_base_seconds
                * (2 ** max(0, sync_job.attempt_count - 1)),
            )
            sync_job.status = SYNC_JOB_STATUS_QUEUED
            sync_job.next_attempt_at = now + timedelta(seconds=delay_seconds)
            sync_job.finished_at = None
            sync_job.error_message = "github sync will retry"
            phase = "retry_scheduled"
        else:
            sync_job.status = SYNC_JOB_STATUS_FAILED
            sync_job.finished_at = now
            sync_job.error_message = "github sync failed"
            phase = SYNC_JOB_STATUS_FAILED
        sync_job.lease_owner = None
        sync_job.lease_expires_at = None
        sync_job.cursor_after = _with_progress_phase(
            sync_job.cursor_after,
            phase=phase,
            now=now,
        )
        sync_job.logs = [
            *(sync_job.logs or []),
            {
                "event": phase,
                "attempt": sync_job.attempt_count,
                "error_code": error_code,
                "at": now.isoformat(),
            },
        ]


async def _locked_claim_job(
    session: AsyncSession,
    claim: GitHubSyncJobClaim,
) -> SyncJob:
    sync_job = await session.scalar(
        select(SyncJob)
        .where(SyncJob.id == claim.id)
        .where(SyncJob.workspace_id == claim.workspace_id)
        .with_for_update()
    )
    if (
        sync_job is None
        or sync_job.status != SYNC_JOB_STATUS_RUNNING
        or sync_job.lease_owner != claim.lease_owner
    ):
        raise GitHubSyncWorkerLostLease
    return sync_job


async def _expire_exhausted_leases(
    session: AsyncSession,
    *,
    now: datetime,
) -> None:
    await session.execute(
        update(SyncJob)
        .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
        .where(SyncJob.status == SYNC_JOB_STATUS_RUNNING)
        .where(SyncJob.lease_expires_at.is_not(None))
        .where(SyncJob.lease_expires_at <= now)
        .where(SyncJob.attempt_count >= SyncJob.max_attempts)
        .values(
            status=SYNC_JOB_STATUS_FAILED,
            finished_at=now,
            error_message="github sync failed",
            lease_owner=None,
            lease_expires_at=None,
        )
    )


def _mark_cancelled(sync_job: SyncJob) -> None:
    now = datetime.now(timezone.utc)
    sync_job.status = SYNC_JOB_STATUS_CANCELLED
    sync_job.finished_at = now
    sync_job.error_message = None
    sync_job.lease_owner = None
    sync_job.lease_expires_at = None
    sync_job.cursor_after = _with_progress_phase(
        sync_job.cursor_after,
        phase=SYNC_JOB_STATUS_CANCELLED,
        now=now,
    )
    sync_job.logs = [
        *(sync_job.logs or []),
        {"event": SYNC_JOB_STATUS_CANCELLED, "at": now.isoformat()},
    ]


def _parse_job_request(
    sync_job: SyncJob,
) -> tuple[GitHubAppLiveSyncInput, str]:
    request = _request_mapping(sync_job.cursor_before)
    connection_id = request.get("connection_id")
    repositories = request.get("repositories")
    issue_states = request.get("issue_states")
    pull_request_states = request.get("pull_request_states")
    if not isinstance(connection_id, str):
        raise GitHubAppLiveSyncError("invalid queued github sync request")
    if not isinstance(repositories, list):
        raise GitHubAppLiveSyncError("invalid queued github sync request")
    try:
        parsed_connection_id = UUID(connection_id)
    except ValueError as exc:
        raise GitHubAppLiveSyncError(
            "invalid queued github sync request"
        ) from exc
    requested_by = request.get("requested_by")
    return (
        GitHubAppLiveSyncInput(
            connection_id=parsed_connection_id,
            repositories=[
                item for item in repositories if isinstance(item, str)
            ],
            include_issues=request.get("include_issues") is not False,
            include_pull_requests=(
                request.get("include_pull_requests") is not False
            ),
            issue_states=(
                [item for item in issue_states if isinstance(item, str)]
                if isinstance(issue_states, list)
                else ["open", "closed"]
            ),
            pull_request_states=(
                [
                    item
                    for item in pull_request_states
                    if isinstance(item, str)
                ]
                if isinstance(pull_request_states, list)
                else ["open", "closed", "merged"]
            ),
        ),
        requested_by if isinstance(requested_by, str) else "operator_api_key",
    )


def _request_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GitHubAppLiveSyncError("invalid queued github sync request")
    request = value.get("github_app_live_sync")
    if not isinstance(request, Mapping):
        raise GitHubAppLiveSyncError("invalid queued github sync request")
    return dict(request)


def _progress(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    progress = value.get("github_app_live_sync_progress")
    return dict(progress) if isinstance(progress, Mapping) else {}


def _with_progress_phase(
    value: dict[str, Any] | None,
    *,
    phase: str,
    now: datetime,
) -> dict[str, Any]:
    progress = _progress(value)
    progress["phase"] = phase
    progress["updated_at"] = now.isoformat()
    return {"github_app_live_sync_progress": progress}


def _counts(value: Any) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    return {
        key: int(source.get(key, 0))
        if isinstance(source.get(key, 0), int)
        else 0
        for key in (
            "repositories",
            "issues",
            "pull_requests",
            "skipped_pull_requests",
        )
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _summary_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _complete_issue_scope(states: tuple[str, ...]) -> bool:
    selected = set(states)
    return "all" in selected or {"open", "closed"}.issubset(selected)


def _complete_pull_request_scope(states: tuple[str, ...]) -> bool:
    selected = set(states)
    return "all" in selected or {"open", "closed", "merged"}.issubset(
        selected
    )
