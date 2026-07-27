from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import PullRequest, Repository, SourceRecord, Task
from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, Membership, User, Workspace
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_SUCCEEDED,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)
from app.db.memory_models import (
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
    CompanyMemoryEvent,
)
from app.services.github_normalization_service import (
    GitHubNormalizationOptions,
    normalize_github_sync_job_local,
)
from app.services.github_operational_read_service import (
    list_workspace_github_operational_work,
)
from app.services.headquarters_read_service import (
    _build_resolved_memory_event_items,
)


async def test_complete_snapshot_tombstones_and_newer_snapshot_restores() -> None:
    marker = uuid4().hex
    repository_full_name = f"acme/reconcile-{marker}"
    external_id = "1001"
    await _cleanup(marker)
    try:
        workspace_id, connection_id = await _seed_workspace(marker)
        now = datetime.now(timezone.utc)
        source_record_id = await _seed_issue(
            workspace_id=workspace_id,
            repository_full_name=repository_full_name,
            external_id=external_id,
            observed_at=now - timedelta(minutes=10),
        )

        tombstone_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[],
        )
        async with AsyncSessionLocal() as session:
            result = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=tombstone_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=True,
                    include_pull_requests=False,
                    persist_if_supported=True,
                    snapshot_observed_at=now - timedelta(minutes=5),
                    provider_attested=True,
                    authoritative_issue_repositories=(repository_full_name,),
                ),
            )
            await session.commit()
        assert result["sync_job"]["status"] == SYNC_JOB_STATUS_SUCCEEDED
        assert result["reconciliation"][0]["records_tombstoned"] == 1

        source_record = await _source_record(source_record_id)
        assert source_record.is_deleted is True
        assert source_record.tombstoned_at is not None
        assert source_record.tombstone_observed_at == now - timedelta(minutes=5)
        assert source_record.tombstone_sync_job_id == tombstone_job_id
        assert (
            source_record.tombstone_reason
            == "missing_from_complete_github_repository_snapshot"
        )
        assert await _operational_issue_ids(workspace_id) == []
        disappeared_item = (await _memory_items(workspace_id))[0]
        assert disappeared_item["kind"] == "source"
        assert disappeared_item["change_type"] == "resolved"
        assert disappeared_item["title"] == f"Источник исчез: issue {external_id}"
        assert disappeared_item["evidence_refs"][0]["provenance"] == (
            "company_memory_event"
        )

        untrusted_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[_raw_issue(repository_full_name, external_id)],
        )
        async with AsyncSessionLocal() as session:
            untrusted = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=untrusted_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=True,
                    include_pull_requests=False,
                    persist_if_supported=True,
                ),
            )
            await session.commit()
        assert untrusted["sync_job"]["records_updated"] == 0
        assert (await _source_record(source_record_id)).is_deleted is True

        stale_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[_raw_issue(repository_full_name, external_id)],
        )
        async with AsyncSessionLocal() as session:
            stale = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=stale_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=True,
                    include_pull_requests=False,
                    persist_if_supported=True,
                    snapshot_observed_at=now - timedelta(minutes=7),
                    provider_attested=True,
                ),
            )
            await session.commit()
        assert stale["sync_job"]["status"] == SYNC_JOB_STATUS_SUCCEEDED
        assert stale["sync_job"]["records_updated"] == 0
        assert (await _source_record(source_record_id)).is_deleted is True

        restore_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[_raw_issue(repository_full_name, external_id)],
        )
        async with AsyncSessionLocal() as session:
            restored = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=restore_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=True,
                    include_pull_requests=False,
                    persist_if_supported=True,
                    snapshot_observed_at=now - timedelta(minutes=4),
                    provider_attested=True,
                    authoritative_issue_repositories=(repository_full_name,),
                ),
            )
            await session.commit()
        assert restored["sync_job"]["status"] == SYNC_JOB_STATUS_SUCCEEDED
        assert (
            restored["sync_job"]["records_updated"] == 1
        )

        source_record = await _source_record(source_record_id)
        assert source_record.is_deleted is False
        assert source_record.tombstoned_at is None
        assert source_record.tombstone_observed_at is None
        assert source_record.tombstone_sync_job_id is None
        assert source_record.tombstone_reason is None
        assert await _operational_issue_ids(workspace_id) == [external_id]
        assert await _memory_event_types(workspace_id) == [
            COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
            COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
        ]
        restored_item = (await _memory_items(workspace_id))[-1]
        assert restored_item["kind"] == "source"
        assert restored_item["change_type"] == "new_or_changed"
        assert restored_item["title"] == f"Источник вернулся: issue {external_id}"
    finally:
        await _cleanup(marker)


async def test_partial_snapshot_never_tombstones_missing_records() -> None:
    marker = uuid4().hex
    repository_full_name = f"acme/partial-{marker}"
    await _cleanup(marker)
    try:
        workspace_id, connection_id = await _seed_workspace(marker)
        source_record_id = await _seed_issue(
            workspace_id=workspace_id,
            repository_full_name=repository_full_name,
            external_id="2002",
            observed_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        sync_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[],
        )

        async with AsyncSessionLocal() as session:
            result = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=sync_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=True,
                    include_pull_requests=False,
                    persist_if_supported=True,
                ),
            )
            await session.commit()

        assert result["sync_job"]["status"] == SYNC_JOB_STATUS_PARTIAL
        assert result["reconciliation"] == []
        assert (await _source_record(source_record_id)).is_deleted is False
        assert await _memory_event_types(workspace_id) == []
    finally:
        await _cleanup(marker)


async def test_complete_pull_request_snapshot_hides_and_restores_projection() -> None:
    marker = uuid4().hex
    repository_full_name = f"acme/pull-reconcile-{marker}"
    external_id = "3003"
    await _cleanup(marker)
    try:
        workspace_id, connection_id = await _seed_workspace(marker)
        now = datetime.now(timezone.utc)
        source_record_id = await _seed_pull_request(
            workspace_id=workspace_id,
            repository_full_name=repository_full_name,
            external_id=external_id,
            observed_at=now - timedelta(minutes=2),
        )
        tombstone_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[],
        )

        async with AsyncSessionLocal() as session:
            result = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=tombstone_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=False,
                    include_pull_requests=True,
                    persist_if_supported=True,
                    snapshot_observed_at=now - timedelta(minutes=1),
                    provider_attested=True,
                    authoritative_pull_request_repositories=(
                        repository_full_name,
                    ),
                ),
            )
            await session.commit()

        assert result["reconciliation"][0]["records_tombstoned"] == 1
        assert (await _source_record(source_record_id)).is_deleted is True
        assert await _operational_pull_request_ids(workspace_id) == []

        restore_job_id = await _seed_sync_job(
            workspace_id=workspace_id,
            connection_id=connection_id,
            issues=[],
            pull_requests=[
                _raw_pull_request(repository_full_name, external_id)
            ],
        )
        async with AsyncSessionLocal() as session:
            restored = await normalize_github_sync_job_local(
                session,
                workspace_id=workspace_id,
                sync_job_id=restore_job_id,
                options=GitHubNormalizationOptions(
                    include_repositories=False,
                    include_issues=False,
                    include_pull_requests=True,
                    persist_if_supported=True,
                    snapshot_observed_at=now + timedelta(seconds=1),
                    provider_attested=True,
                    authoritative_pull_request_repositories=(
                        repository_full_name,
                    ),
                ),
            )
            await session.commit()

        assert restored["sync_job"]["status"] == SYNC_JOB_STATUS_SUCCEEDED
        assert (await _source_record(source_record_id)).is_deleted is False
        assert await _operational_pull_request_ids(workspace_id) == [external_id]
    finally:
        await _cleanup(marker)


async def _seed_workspace(marker: str) -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"source-reconciliation-{marker}@example.test",
            name="Source Reconciliation Owner",
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Source Reconciliation {marker}",
            slug=f"source-reconciliation-{marker}",
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
            status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
            display_name="GitHub reconciliation",
            external_account_id=f"reconciliation-{marker}",
            scopes=["repo"],
            provider_metadata={"connection_method": "test"},
        )
        session.add(connection)
        await session.commit()
        return workspace.id, connection.id


async def _seed_issue(
    *,
    workspace_id: UUID,
    repository_full_name: str,
    external_id: str,
    observed_at: datetime,
) -> UUID:
    payload = {
        "record_type": "issue",
        "normalized_issue": {
            "external_id": external_id,
            "repository_full_name": repository_full_name,
        },
        "evidence_refs": [],
    }
    async with AsyncSessionLocal() as session:
        source_record = SourceRecord(
            workspace_id=workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            external_id=external_id,
            record_type="issue",
            source_url=(
                f"https://github.com/{repository_full_name}/issues/1"
            ),
            payload=payload,
            payload_hash=f"seed-{external_id}",
            observed_at=observed_at,
            is_deleted=False,
        )
        session.add(source_record)
        await session.flush()
        session.add(
            Task(
                workspace_id=workspace_id,
                source_provider=INTEGRATION_PROVIDER_GITHUB,
                source_record_id=source_record.id,
                external_id=external_id,
                title="Reconciled issue",
                status="open",
                task_metadata={
                    "github_object_type": "issue",
                    "repository_full_name": repository_full_name,
                    "number": 1,
                },
            )
        )
        await session.commit()
        return source_record.id


async def _seed_sync_job(
    *,
    workspace_id: UUID,
    connection_id: UUID,
    issues: list[dict],
    pull_requests: list[dict] | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        sync_job = SyncJob(
            workspace_id=workspace_id,
            connection_id=connection_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            status=SYNC_JOB_STATUS_QUEUED,
            sync_type=SYNC_JOB_TYPE_MANUAL,
            cursor_before={
                "local_github": {
                    "repositories": [],
                    "issues": issues,
                    "pull_requests": pull_requests or [],
                }
            },
            records_seen=0,
            records_created=0,
            records_updated=0,
            logs=[],
        )
        session.add(sync_job)
        await session.commit()
        return sync_job.id


def _raw_issue(repository_full_name: str, external_id: str) -> dict:
    return {
        "id": external_id,
        "number": 1,
        "title": "Reconciled issue",
        "state": "open",
        "repository_full_name": repository_full_name,
        "html_url": f"https://github.com/{repository_full_name}/issues/1",
        "updated_at": "2026-07-27T12:00:00Z",
    }


async def _seed_pull_request(
    *,
    workspace_id: UUID,
    repository_full_name: str,
    external_id: str,
    observed_at: datetime,
) -> UUID:
    payload = {
        "record_type": "pull_request",
        "normalized_pull_request": {
            "external_id": external_id,
            "repository_full_name": repository_full_name,
        },
        "evidence_refs": [],
    }
    async with AsyncSessionLocal() as session:
        source_record = SourceRecord(
            workspace_id=workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            external_id=external_id,
            record_type="pull_request",
            source_url=f"https://github.com/{repository_full_name}/pull/2",
            payload=payload,
            payload_hash=f"seed-pull-{external_id}",
            observed_at=observed_at,
            is_deleted=False,
        )
        repository = Repository(
            workspace_id=workspace_id,
            provider=INTEGRATION_PROVIDER_GITHUB,
            external_id=repository_full_name,
            name=repository_full_name.rsplit("/", 1)[-1],
            full_name=repository_full_name,
            visibility="private",
        )
        session.add_all([source_record, repository])
        await session.flush()
        session.add(
            PullRequest(
                workspace_id=workspace_id,
                repository_id=repository.id,
                source_record_id=source_record.id,
                external_id=external_id,
                number=2,
                title="Reconciled pull request",
                state="open",
                pr_metadata={
                    "github_object_type": "pull_request",
                    "repository_full_name": repository_full_name,
                    "number": 2,
                },
            )
        )
        await session.commit()
        return source_record.id


def _raw_pull_request(repository_full_name: str, external_id: str) -> dict:
    return {
        "id": external_id,
        "number": 2,
        "title": "Reconciled pull request",
        "state": "open",
        "repository_full_name": repository_full_name,
        "html_url": f"https://github.com/{repository_full_name}/pull/2",
        "updated_at": "2026-07-27T12:00:00Z",
    }


async def _source_record(source_record_id: UUID) -> SourceRecord:
    async with AsyncSessionLocal() as session:
        source_record = await session.get(SourceRecord, source_record_id)
        assert source_record is not None
        session.expunge(source_record)
        return source_record


async def _operational_issue_ids(workspace_id: UUID) -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await list_workspace_github_operational_work(
            session=session,
            workspace_id=workspace_id,
            state="all",
        )
        return [str(issue["external_id"]) for issue in result["issues"]]


async def _operational_pull_request_ids(workspace_id: UUID) -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await list_workspace_github_operational_work(
            session=session,
            workspace_id=workspace_id,
            state="all",
        )
        return [
            str(pull_request["external_id"])
            for pull_request in result["pull_requests"]
        ]


async def _memory_event_types(workspace_id: UUID) -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(CompanyMemoryEvent)
                .where(CompanyMemoryEvent.workspace_id == workspace_id)
                .order_by(CompanyMemoryEvent.workspace_sequence.asc())
            )
        ).scalars()
        return [row.event_type for row in rows]


async def _memory_items(workspace_id: UUID) -> list[dict]:
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.execute(
                    select(CompanyMemoryEvent)
                    .where(CompanyMemoryEvent.workspace_id == workspace_id)
                    .order_by(CompanyMemoryEvent.workspace_sequence.asc())
                )
            ).scalars()
        )
        return await _build_resolved_memory_event_items(
            session=session,
            workspace_id=workspace_id,
            events=events,
        )


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"source-reconciliation-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(
                            f"source-reconciliation-{marker}%@example.test"
                        )
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(CompanyMemoryEvent).where(
                    CompanyMemoryEvent.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Task).where(Task.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(PullRequest).where(
                    PullRequest.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Repository).where(
                    Repository.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(SourceRecord).where(
                    SourceRecord.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(
                    Membership.workspace_id.in_(workspace_ids)
                )
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
