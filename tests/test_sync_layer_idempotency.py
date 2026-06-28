"""Idempotency + concurrency contract for the remaining GitHub sync upserts.

Mirrors tests/test_task_upsert_idempotency.py for SourceRecord and PullRequest.
Runs against the real PostgreSQL substrate so INSERT ... ON CONFLICT semantics
against the existing unique constraints are genuinely exercised.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import (
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.identity_models import User, Workspace
from app.services.github_normalization_service import (
    SOURCE_RECORD_TYPE_ISSUE,
    _upsert_pull_request,
    _upsert_repository,
    _upsert_source_record,
)


async def _seed_workspace(marker: str) -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as session:
        user = User(email=f"sync-idem-{marker}@example.test", name="Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Sync Idem {marker}",
            slug=f"sync-idem-{marker}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        await session.commit()
        return user.id, workspace.id


async def _seed_repository(workspace_id: UUID, marker: str) -> UUID:
    async with AsyncSessionLocal() as session:
        repo = Repository(
            workspace_id=workspace_id,
            external_id=f"qtwin-io/repo-{marker}",
            name=f"repo-{marker}",
            full_name=f"qtwin-io/repo-{marker}",
        )
        session.add(repo)
        await session.flush()
        await session.commit()
        return repo.id


async def _cleanup(user_id: UUID, workspace_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Task).where(Task.workspace_id == workspace_id))
        await session.execute(
            delete(PullRequest).where(PullRequest.workspace_id == workspace_id)
        )
        await session.execute(
            delete(SourceRecord).where(SourceRecord.workspace_id == workspace_id)
        )
        await session.execute(
            delete(Repository).where(Repository.workspace_id == workspace_id)
        )
        await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


# --- SourceRecord -----------------------------------------------------------


async def _upsert_source_record_once(workspace_id: UUID, external_id: str, payload_marker: str) -> bool:
    async with AsyncSessionLocal() as session:
        _, created = await _upsert_source_record(
            session,
            sync_job=SimpleNamespace(workspace_id=workspace_id, connection_id=None, id=None),
            external_id=external_id,
            record_type=SOURCE_RECORD_TYPE_ISSUE,
            payload={"record_type": SOURCE_RECORD_TYPE_ISSUE, "marker": payload_marker},
            source_url="https://github.com/qtwin-io/repo/issues/1",
            source_updated_at=None,
            observed_at=datetime.now(timezone.utc),
        )
        await session.commit()
        return created


async def test_source_record_upsert_is_idempotent_sequentially() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    external_id = f"qtwin-io/repo#issue-{marker}"
    try:
        first = await _upsert_source_record_once(workspace_id, external_id, "v1")
        second = await _upsert_source_record_once(workspace_id, external_id, "v2")
        assert first is True
        assert second is False
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.external_id == external_id)
            )
            row = await session.scalar(
                select(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.external_id == external_id)
            )
        assert count == 1
        assert row is not None and row.payload["marker"] == "v2"
    finally:
        await _cleanup(user_id, workspace_id)


async def test_source_record_upsert_concurrent_yields_single_row() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    external_id = f"qtwin-io/repo#issue-{marker}"
    try:
        results = await asyncio.gather(
            *(_upsert_source_record_once(workspace_id, external_id, "x") for _ in range(5))
        )
        assert sum(1 for created in results if created) == 1
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(SourceRecord.workspace_id == workspace_id)
                .where(SourceRecord.external_id == external_id)
            )
        assert count == 1
    finally:
        await _cleanup(user_id, workspace_id)


# --- PullRequest ------------------------------------------------------------


def _pr(external_id: str, *, title: str = "PR") -> dict:
    return {
        "external_id": external_id,
        "number": 7,
        "title": title,
        "state": "open",
        "source_url": "https://github.com/qtwin-io/repo/pull/7",
        "repository_full_name": "qtwin-io/repo",
    }


async def _upsert_pull_request_once(
    workspace_id: UUID, repository_id: UUID, external_id: str, title: str
) -> bool:
    async with AsyncSessionLocal() as session:
        created = await _upsert_pull_request(
            session,
            sync_job=SimpleNamespace(workspace_id=workspace_id),
            pull_request=_pr(external_id, title=title),
            repository=SimpleNamespace(id=repository_id),
        )
        await session.commit()
        return created


async def test_pull_request_upsert_is_idempotent_sequentially() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    repo_id = await _seed_repository(workspace_id, marker)
    external_id = f"qtwin-io/repo#pr-{marker}"
    try:
        first = await _upsert_pull_request_once(workspace_id, repo_id, external_id, "v1")
        second = await _upsert_pull_request_once(workspace_id, repo_id, external_id, "v2")
        assert first is True
        assert second is False
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PullRequest)
                .where(PullRequest.workspace_id == workspace_id)
                .where(PullRequest.external_id == external_id)
            )
            row = await session.scalar(
                select(PullRequest)
                .where(PullRequest.workspace_id == workspace_id)
                .where(PullRequest.external_id == external_id)
            )
        assert count == 1
        assert row is not None and row.title == "v2"
    finally:
        await _cleanup(user_id, workspace_id)


async def test_pull_request_upsert_concurrent_yields_single_row() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    repo_id = await _seed_repository(workspace_id, marker)
    external_id = f"qtwin-io/repo#pr-{marker}"
    try:
        results = await asyncio.gather(
            *(_upsert_pull_request_once(workspace_id, repo_id, external_id, "x") for _ in range(5))
        )
        assert sum(1 for created in results if created) == 1
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PullRequest)
                .where(PullRequest.workspace_id == workspace_id)
                .where(PullRequest.external_id == external_id)
            )
        assert count == 1
    finally:
        await _cleanup(user_id, workspace_id)


# --- Repository -------------------------------------------------------------


def _repo(full_name: str, *, default_branch: str = "main") -> dict:
    return {
        "full_name": full_name,
        "name": full_name.rsplit("/", 1)[-1],
        "visibility": "private",
        "default_branch": default_branch,
        "archived": False,
        "source_url": f"https://github.com/{full_name}",
        "last_activity_at": "2026-06-28T10:00:00Z",
        "metadata": {"source": "test"},
    }


async def _upsert_repository_once(
    workspace_id: UUID, external_id: str, full_name: str, default_branch: str = "main"
) -> tuple[bool, UUID]:
    async with AsyncSessionLocal() as session:
        repository, created = await _upsert_repository(
            session,
            sync_job=SimpleNamespace(workspace_id=workspace_id),
            repo=_repo(full_name, default_branch=default_branch),
            external_id=external_id,
        )
        repo_id = repository.id  # read before commit (expire_on_commit)
        await session.commit()
        return created, repo_id


async def _count_repositories(workspace_id: UUID, full_name: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(Repository)
            .where(Repository.workspace_id == workspace_id)
            .where(Repository.full_name == full_name)
        )


async def test_repository_upsert_is_idempotent_sequentially() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    full_name = f"qtwin-io/repo-{marker}"
    external_id = f"gh-id-{marker}"
    try:
        first_created, first_id = await _upsert_repository_once(
            workspace_id, external_id, full_name, default_branch="main"
        )
        second_created, second_id = await _upsert_repository_once(
            workspace_id, external_id, full_name, default_branch="develop"
        )
        assert first_created is True
        assert second_created is False
        assert first_id == second_id  # same row, no duplicate
        assert await _count_repositories(workspace_id, full_name) == 1
        async with AsyncSessionLocal() as session:
            row = await session.get(Repository, first_id)
            assert row is not None and row.default_branch == "develop"  # updated
    finally:
        await _cleanup(user_id, workspace_id)


async def test_repository_upsert_concurrent_yields_single_row() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    full_name = f"qtwin-io/repo-{marker}"
    external_id = f"gh-id-{marker}"
    try:
        results = await asyncio.gather(
            *(
                _upsert_repository_once(workspace_id, external_id, full_name)
                for _ in range(5)
            )
        )
        assert sum(1 for created, _ in results if created) == 1
        assert await _count_repositories(workspace_id, full_name) == 1
    finally:
        await _cleanup(user_id, workspace_id)


async def test_repository_upsert_dedupes_across_external_id_and_full_name() -> None:
    # Load-bearing cross-path dedup: a repo first seen via the work-item path
    # (external_id == full_name) and later via the main sync (external_id ==
    # numeric id) must converge onto ONE row, not duplicate.
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    full_name = f"qtwin-io/repo-{marker}"
    try:
        work_item_created, work_item_id = await _upsert_repository_once(
            workspace_id, full_name, full_name
        )
        main_created, main_id = await _upsert_repository_once(
            workspace_id, f"gh-id-{marker}", full_name
        )
        assert work_item_created is True
        assert main_created is False  # resolved via full_name fallback
        assert work_item_id == main_id  # same row
        assert await _count_repositories(workspace_id, full_name) == 1
        async with AsyncSessionLocal() as session:
            row = await session.get(Repository, main_id)
            # external_id was migrated to the numeric id on the second upsert.
            assert row is not None and row.external_id == f"gh-id-{marker}"
    finally:
        await _cleanup(user_id, workspace_id)
