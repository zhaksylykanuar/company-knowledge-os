"""Idempotency + concurrency contract for the canonical GitHub issue -> Task upsert.

These run against the real PostgreSQL substrate (not SQLite) so the partial
unique index and INSERT ... ON CONFLICT semantics are genuinely exercised.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import TASK_PROVIDER_GITHUB, SourceRecord, Task
from app.db.identity_models import User, Workspace
from app.services.github_normalization_service import _upsert_github_issue_task


def _issue(external_id: str, *, title: str = "Concurrent issue") -> dict:
    return {
        "external_id": external_id,
        "title": title,
        "description": "body",
        "state": "open",
        "source_url": f"https://github.com/qtwin-io/repo/issues/{external_id[-1]}",
        "number": 1,
        "repository_full_name": "qtwin-io/repo",
    }


async def _seed_workspace_and_source_record(marker: str) -> tuple[UUID, UUID, UUID]:
    """Create a user, workspace, and source record; return their ids."""

    async with AsyncSessionLocal() as session:
        user = User(email=f"task-upsert-{marker}@example.test", name="Owner")
        session.add(user)
        await session.flush()

        workspace = Workspace(
            name=f"Task Upsert {marker}",
            slug=f"task-upsert-{marker}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()

        source_record = SourceRecord(
            workspace_id=workspace.id,
            provider="github",
            external_id=f"qtwin-io/repo#issue-{marker}",
            record_type="github_issue",
            payload={},
            payload_hash="hash",
            observed_at=datetime.now(timezone.utc),
        )
        session.add(source_record)
        await session.flush()

        await session.commit()
        return user.id, workspace.id, source_record.id


async def _cleanup(user_id: UUID, workspace_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Task).where(Task.workspace_id == workspace_id))
        await session.execute(
            delete(SourceRecord).where(SourceRecord.workspace_id == workspace_id)
        )
        await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _count_tasks(workspace_id: UUID, external_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.workspace_id == workspace_id)
            .where(Task.source_provider == TASK_PROVIDER_GITHUB)
            .where(Task.external_id == external_id)
        )


async def _run_upsert(workspace_id: UUID, source_record_id: UUID, issue: dict) -> bool:
    async with AsyncSessionLocal() as session:
        created = await _upsert_github_issue_task(
            session,
            sync_job=SimpleNamespace(workspace_id=workspace_id),
            issue=issue,
            source_record=SimpleNamespace(id=source_record_id),
            source_updated_at=None,
        )
        await session.commit()
        return created


async def test_task_upsert_is_idempotent_sequentially() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, source_record_id = await _seed_workspace_and_source_record(marker)
    external_id = f"qtwin-io/repo#issue-{marker}"
    try:
        first = await _run_upsert(workspace_id, source_record_id, _issue(external_id, title="v1"))
        second = await _run_upsert(workspace_id, source_record_id, _issue(external_id, title="v2"))

        assert first is True  # inserted
        assert second is False  # updated, not a new row
        assert await _count_tasks(workspace_id, external_id) == 1

        # The update path applied the new mutable values to the single row.
        async with AsyncSessionLocal() as session:
            task = await session.scalar(
                select(Task)
                .where(Task.workspace_id == workspace_id)
                .where(Task.external_id == external_id)
            )
            assert task is not None
            assert task.title == "v2"
    finally:
        await _cleanup(user_id, workspace_id)


async def test_task_upsert_concurrent_yields_single_task_no_integrityerror() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, source_record_id = await _seed_workspace_and_source_record(marker)
    external_id = f"qtwin-io/repo#issue-{marker}"
    try:
        # Five overlapping syncs for the SAME issue, each in its own session /
        # connection. With ON CONFLICT DO UPDATE this must not raise an
        # IntegrityError, and the DB must converge to exactly one row.
        results = await asyncio.gather(
            *(
                _run_upsert(workspace_id, source_record_id, _issue(external_id))
                for _ in range(5)
            )
        )

        # Exactly one execution performed the INSERT (xmax = 0); the rest updated.
        assert sum(1 for created in results if created) == 1
        assert await _count_tasks(workspace_id, external_id) == 1
    finally:
        await _cleanup(user_id, workspace_id)


async def test_partial_index_allows_multiple_null_external_id_tasks() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, source_record_id = await _seed_workspace_and_source_record(marker)
    try:
        # Manual / internal tasks carry NULL external_id and must never collide
        # under the partial unique index (WHERE external_id IS NOT NULL).
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    Task(
                        workspace_id=workspace_id,
                        source_provider="internal",
                        external_id=None,
                        title="manual one",
                    ),
                    Task(
                        workspace_id=workspace_id,
                        source_provider="internal",
                        external_id=None,
                        title="manual two",
                    ),
                ]
            )
            await session.commit()  # must NOT raise IntegrityError

        async with AsyncSessionLocal() as session:
            null_count = await session.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.workspace_id == workspace_id)
                .where(Task.external_id.is_(None))
            )
            assert null_count == 2
    finally:
        await _cleanup(user_id, workspace_id)
