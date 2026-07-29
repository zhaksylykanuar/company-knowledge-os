from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import EvidenceRef, PullRequest, Repository, SourceRecord, Task
from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, Membership, User, Workspace
from app.db.integration_models import (
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_CANCELLED,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_RUNNING,
    SYNC_JOB_STATUS_SUCCEEDED,
    IntegrationConnection,
    SyncJob,
)
from app.services.github_app_live_sync_service import (
    GitHubAppLiveSyncPrepared,
    GitHubAppLiveSyncProviderReadError,
    GitHubAppProviderContext,
    GitHubRepositoryBatch,
)
from app.services.github_sync_job_service import (
    request_github_sync_job_cancellation,
)
from app.services import github_sync_worker_service


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"sync-worker-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"sync-worker-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            for model in (
                EvidenceRef,
                PullRequest,
                Task,
                Repository,
                SourceRecord,
                SyncJob,
                IntegrationConnection,
                Membership,
            ):
                await session.execute(
                    delete(model).where(model.workspace_id.in_(workspace_ids))
                )
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(
                delete(Membership).where(Membership.user_id.in_(user_ids))
            )
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _seed_job(
    marker: str,
    *,
    repositories: tuple[str, ...] = ("owner/repo-a",),
    status: str = SYNC_JOB_STATUS_QUEUED,
    attempt_count: int = 0,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    completed_repositories: tuple[str, ...] = (),
) -> tuple[UUID, UUID, UUID]:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"sync-worker-{marker}@example.test",
            name="Sync Worker Owner",
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name="Sync Worker",
            slug=f"sync-worker-{marker}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )
        )
        connection = IntegrationConnection(
            workspace_id=workspace.id,
            provider=INTEGRATION_PROVIDER_GITHUB,
        )
        session.add(connection)
        await session.flush()
        job = SyncJob(
            workspace_id=workspace.id,
            connection_id=connection.id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            status=status,
            cursor_before={
                "github_app_live_sync": {
                    "connection_id": str(connection.id),
                    "installation_id": "123",
                    "repositories": list(repositories),
                    "include_issues": False,
                    "include_pull_requests": False,
                    "issue_states": ["open", "closed"],
                    "pull_request_states": ["open", "closed", "merged"],
                    "requested_by": "session",
                    "external_writes": False,
                    "installation_access_token_persisted": False,
                }
            },
            cursor_after={
                "github_app_live_sync_progress": {
                    "phase": status,
                    "completed_repositories": list(completed_repositories),
                    "total_repositories": len(repositories),
                    "repositories": [
                        {
                            "full_name": repository,
                            "synced_issues": 0,
                            "synced_pull_requests": 0,
                            "skipped_pull_requests": 0,
                        }
                        for repository in completed_repositories
                    ],
                    "counts": {
                        "repositories": len(completed_repositories),
                        "issues": 0,
                        "pull_requests": 0,
                        "skipped_pull_requests": 0,
                    },
                    "updated_at": now.isoformat(),
                }
            },
            attempt_count=attempt_count,
            max_attempts=3,
            next_attempt_at=now - timedelta(seconds=1),
            lease_owner=lease_owner,
            lease_expires_at=lease_expires_at,
            started_at=now if status == SYNC_JOB_STATUS_RUNNING else None,
            records_seen=len(completed_repositories),
        )
        session.add(job)
        await session.commit()
        return workspace.id, connection.id, job.id


def _prepared(
    workspace_id: UUID,
    connection_id: UUID,
    repositories: tuple[str, ...],
) -> GitHubAppLiveSyncPrepared:
    return GitHubAppLiveSyncPrepared(
        workspace_id=workspace_id,
        connection_id=connection_id,
        installation_id="123",
        repositories=repositories,
        include_issues=False,
        include_pull_requests=False,
        issue_states=("open", "closed"),
        pull_request_states=("open", "closed", "merged"),
        credential=None,
    )


def _batch(repository: str) -> GitHubRepositoryBatch:
    observed_at = datetime.now(timezone.utc)
    return GitHubRepositoryBatch(
        full_name=repository,
        observed_at=observed_at,
        repository={
            "id": repository,
            "external_id": repository,
            "name": repository.rsplit("/", 1)[-1],
            "full_name": repository,
            "default_branch": "main",
            "visibility": "private",
            "archived": False,
            "source_url": f"https://github.com/{repository}",
            "last_activity_at": observed_at.isoformat(),
            "source": "github_app_live_sync",
            "evidence_refs": [
                {
                    "kind": "github_repository",
                    "source": "github",
                    "ref": repository,
                    "url": f"https://github.com/{repository}",
                }
            ],
            "metadata": {"source": "github_app_live_sync"},
        },
        issues=[],
        pull_requests=[],
        skipped_pull_requests=0,
    )


async def _stored_job(job_id: UUID) -> SyncJob:
    async with AsyncSessionLocal() as session:
        job = await session.scalar(select(SyncJob).where(SyncJob.id == job_id))
        assert job is not None
        return job


async def test_two_workers_atomically_claim_one_job_once() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        _workspace_id, _connection_id, job_id = await _seed_job(marker)

        async def claim(worker_id: str):
            async with AsyncSessionLocal() as session, session.begin():
                return await github_sync_worker_service.claim_next_github_sync_job(
                    session,
                    worker_id=worker_id,
                )

        claims = await asyncio.gather(claim("one"), claim("two"))
        assert sum(item is not None for item in claims) == 1
        stored = await _stored_job(job_id)
        assert stored.status == SYNC_JOB_STATUS_RUNNING
        assert stored.attempt_count == 1
        assert stored.lease_owner is not None
        assert stored.lease_expires_at is not None
    finally:
        await _cleanup(marker)


async def test_invalid_queued_request_fails_once_instead_of_hot_looping() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        _workspace_id, _connection_id, job_id = await _seed_job(marker)
        async with AsyncSessionLocal() as session:
            job = await session.scalar(
                select(SyncJob).where(SyncJob.id == job_id)
            )
            assert job is not None
            job.cursor_before = {"github_app_live_sync": {"repositories": []}}
            await session.commit()

        async with httpx.AsyncClient() as client:
            processed = (
                await github_sync_worker_service.process_one_github_sync_job(
                    client=client,
                    worker_id="invalid-request-test",
                )
            )

        assert processed is False
        stored = await _stored_job(job_id)
        assert stored.status == "failed"
        assert stored.error_message == "github sync failed"
        assert stored.lease_owner is None
        assert stored.cursor_after is not None
        assert (
            stored.cursor_after["github_app_live_sync_progress"]["phase"]
            == "failed"
        )
    finally:
        await _cleanup(marker)


async def test_provider_io_starts_after_claim_transaction_is_closed(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace_id, connection_id, job_id = await _seed_job(marker)
        prepared = _prepared(workspace_id, connection_id, ("owner/repo-a",))

        async def fake_prepare(_claim):
            return prepared

        async def fake_open(_prepared, *, client):
            assert client is not None
            async with AsyncSessionLocal() as session, session.begin():
                locked = await session.scalar(
                    select(SyncJob)
                    .where(SyncJob.id == job_id)
                    .with_for_update(nowait=True)
                )
                assert locked is not None
                assert locked.status == SYNC_JOB_STATUS_RUNNING
            return GitHubAppProviderContext(
                access_token="in-memory-only",
                installation_token_expires_at=None,
                installed_repositories={
                    "owner/repo-a": {"full_name": "owner/repo-a"}
                },
            )

        async def fake_read(
            _prepared,
            _provider,
            *,
            repository_full_name,
            client,
        ):
            assert client is not None
            return _batch(repository_full_name)

        monkeypatch.setattr(
            github_sync_worker_service,
            "_prepare_claim",
            fake_prepare,
        )
        monkeypatch.setattr(
            github_sync_worker_service,
            "open_github_app_provider_context",
            fake_open,
        )
        monkeypatch.setattr(
            github_sync_worker_service,
            "read_github_app_repository_batch",
            fake_read,
        )
        async with httpx.AsyncClient() as client:
            assert (
                await github_sync_worker_service.process_one_github_sync_job(
                    client=client,
                    worker_id="transaction-test",
                )
                is True
            )
        stored = await _stored_job(job_id)
        assert stored.status == SYNC_JOB_STATUS_SUCCEEDED
        assert stored.cursor_before is not None
        assert "local_github" not in stored.cursor_before
        assert "in-memory-only" not in str(stored.cursor_before)
        assert "in-memory-only" not in str(stored.cursor_after)
    finally:
        await _cleanup(marker)


async def test_transient_provider_failure_schedules_bounded_retry(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace_id, connection_id, job_id = await _seed_job(marker)
        prepared = _prepared(workspace_id, connection_id, ("owner/repo-a",))

        async def fake_prepare(_claim):
            return prepared

        async def fail_open(_prepared, *, client):
            assert client is not None
            raise GitHubAppLiveSyncProviderReadError(
                "private-provider-detail-must-not-persist"
            )

        monkeypatch.setattr(
            github_sync_worker_service,
            "_prepare_claim",
            fake_prepare,
        )
        monkeypatch.setattr(
            github_sync_worker_service,
            "open_github_app_provider_context",
            fail_open,
        )
        async with httpx.AsyncClient() as client:
            assert await github_sync_worker_service.process_one_github_sync_job(
                client=client,
                worker_id="retry-test",
            )
        stored = await _stored_job(job_id)
        assert stored.status == SYNC_JOB_STATUS_QUEUED
        assert stored.attempt_count == 1
        assert stored.next_attempt_at > datetime.now(timezone.utc)
        serialized = f"{stored.error_message} {stored.logs} {stored.cursor_after}"
        assert "private-provider-detail" not in serialized
        assert "github_provider_read_failed" in serialized
    finally:
        await _cleanup(marker)


async def test_stale_lease_resumes_after_completed_repository(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    repositories = ("owner/repo-a", "owner/repo-b")
    try:
        workspace_id, connection_id, job_id = await _seed_job(
            marker,
            repositories=repositories,
            status=SYNC_JOB_STATUS_RUNNING,
            attempt_count=1,
            lease_owner="dead-worker",
            lease_expires_at=datetime.now(timezone.utc)
            - timedelta(seconds=1),
            completed_repositories=("owner/repo-a",),
        )
        prepared = _prepared(workspace_id, connection_id, repositories)
        reads: list[str] = []

        async def fake_prepare(_claim):
            return prepared

        async def fake_open(_prepared, *, client):
            return GitHubAppProviderContext(
                access_token="in-memory-only",
                installation_token_expires_at=None,
                installed_repositories={
                    repository.casefold(): {"full_name": repository}
                    for repository in repositories
                },
            )

        async def fake_read(
            _prepared,
            _provider,
            *,
            repository_full_name,
            client,
        ):
            reads.append(repository_full_name)
            return _batch(repository_full_name)

        monkeypatch.setattr(
            github_sync_worker_service,
            "_prepare_claim",
            fake_prepare,
        )
        monkeypatch.setattr(
            github_sync_worker_service,
            "open_github_app_provider_context",
            fake_open,
        )
        monkeypatch.setattr(
            github_sync_worker_service,
            "read_github_app_repository_batch",
            fake_read,
        )
        async with httpx.AsyncClient() as client:
            assert await github_sync_worker_service.process_one_github_sync_job(
                client=client,
                worker_id="resume-test",
            )
        assert reads == ["owner/repo-b"]
        stored = await _stored_job(job_id)
        assert stored.status == SYNC_JOB_STATUS_SUCCEEDED
        assert stored.attempt_count == 2
        progress = stored.cursor_after["github_app_live_sync_progress"]
        assert progress["completed_repositories"] == list(repositories)
    finally:
        await _cleanup(marker)


async def test_cancellation_revokes_running_lease_immediately() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace_id, _connection_id, job_id = await _seed_job(
            marker,
            status=SYNC_JOB_STATUS_RUNNING,
            attempt_count=1,
            lease_owner="active-worker",
            lease_expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=5),
        )
        async with AsyncSessionLocal() as session:
            result = await request_github_sync_job_cancellation(
                session,
                workspace_id=workspace_id,
                sync_job_id=job_id,
                requested_by="session",
            )
            await session.commit()
        assert result["status"] == SYNC_JOB_STATUS_CANCELLED
        assert result["execution_started"] is True
        assert result["is_live"] is True
        stored = await _stored_job(job_id)
        assert stored.status == SYNC_JOB_STATUS_CANCELLED
        assert stored.cancel_requested_at is not None
        assert stored.lease_owner is None
        assert stored.lease_expires_at is None
    finally:
        await _cleanup(marker)


async def test_cancelling_queued_job_does_not_claim_provider_execution() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace_id, _connection_id, job_id = await _seed_job(marker)
        async with AsyncSessionLocal() as session:
            result = await request_github_sync_job_cancellation(
                session,
                workspace_id=workspace_id,
                sync_job_id=job_id,
                requested_by="session",
            )
            await session.commit()

        assert result["status"] == SYNC_JOB_STATUS_CANCELLED
        assert result["execution_started"] is False
        assert result["is_live"] is False
    finally:
        await _cleanup(marker)
