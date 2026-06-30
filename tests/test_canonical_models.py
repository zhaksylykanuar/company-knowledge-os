"""Tests for the canonical §6 spine models (FOS-002, DEC-028).

Covers create/roundtrip, the workspace/provider/external_id uniqueness,
check constraints, FK enforcement, and that the migration created the tables,
constraints, and indexes.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import (
    PULL_REQUEST_STATE_OPEN,
    REPOSITORY_VISIBILITY_PRIVATE,
    SOURCE_RECORD_PROVIDER_GITHUB,
    TASK_PROVIDER_GITHUB,
    EvidenceRef,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, Membership, User, Workspace


async def _create_workspace(marker: str) -> Workspace:
    async with AsyncSessionLocal() as session:
        user = User(email=f"canonical-{marker}@example.test", name="Canonical Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name="Canonical Workspace",
            slug=f"canonical-{marker}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id, user_id=user.id, role=MEMBERSHIP_ROLE_OWNER
            )
        )
        await session.commit()
        return workspace


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"canonical-{marker}%"))
                )
            ).scalars()
        )
        if workspace_ids:
            for model in (EvidenceRef, Task, PullRequest, Repository, SourceRecord, Membership):
                await session.execute(
                    delete(model).where(model.workspace_id.in_(workspace_ids))
                )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        await session.execute(
            delete(User).where(User.email.like(f"canonical-{marker}@example.test"))
        )
        await session.commit()


def test_canonical_models_register_with_metadata() -> None:
    assert SourceRecord.__tablename__ == "source_records"
    assert EvidenceRef.__tablename__ == "evidence_refs"
    assert Repository.__tablename__ == "repositories"
    assert PullRequest.__tablename__ == "pull_requests"
    assert Task.__tablename__ == "tasks"
    # metadata-reserved attr is mapped to the "metadata" column on each table.
    assert Repository.__table__.c.metadata.name == "metadata"
    assert PullRequest.__table__.c.metadata.name == "metadata"
    assert Task.__table__.c.metadata.name == "metadata"


async def test_spine_create_and_roundtrip() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace = await _create_workspace(marker)
        observed = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

        async with AsyncSessionLocal() as session:
            source_record = SourceRecord(
                workspace_id=workspace.id,
                provider=SOURCE_RECORD_PROVIDER_GITHUB,
                external_id=f"repo-{marker}",
                record_type="repository",
                source_url="https://github.com/acme/repo",
                payload={"full_name": "acme/repo", "private": True},
                payload_hash="hash-" + marker,
                observed_at=observed,
            )
            session.add(source_record)
            await session.flush()

            repository = Repository(
                workspace_id=workspace.id,
                external_id=f"repo-{marker}",
                name="repo",
                full_name="acme/repo",
                default_branch="main",
                visibility=REPOSITORY_VISIBILITY_PRIVATE,
                source_url="https://github.com/acme/repo",
                repo_metadata={"stars": 3},
            )
            session.add(repository)
            await session.flush()

            pull_request = PullRequest(
                workspace_id=workspace.id,
                repository_id=repository.id,
                external_id=f"pr-{marker}",
                number=7,
                title="Add feature",
                state=PULL_REQUEST_STATE_OPEN,
                source_url="https://github.com/acme/repo/pull/7",
            )
            session.add(pull_request)

            task = Task(
                workspace_id=workspace.id,
                source_provider=TASK_PROVIDER_GITHUB,
                source_record_id=source_record.id,
                external_id=f"issue-{marker}",
                title="Fix bug",
                status="open",
                due_date=date(2026, 7, 1),
            )
            session.add(task)

            evidence = EvidenceRef(
                workspace_id=workspace.id,
                source_record_id=source_record.id,
                quote="acme/repo",
                field_path="full_name",
                confidence=0.9,
            )
            session.add(evidence)
            await session.commit()

            sr_id, repo_id, pr_id, task_id, ev_id = (
                source_record.id,
                repository.id,
                pull_request.id,
                task.id,
                evidence.id,
            )

        async with AsyncSessionLocal() as session:
            stored_sr = await session.scalar(
                select(SourceRecord).where(SourceRecord.id == sr_id)
            )
            stored_repo = await session.scalar(
                select(Repository).where(Repository.id == repo_id)
            )
            stored_pr = await session.scalar(
                select(PullRequest).where(PullRequest.id == pr_id)
            )
            stored_task = await session.scalar(select(Task).where(Task.id == task_id))
            stored_ev = await session.scalar(
                select(EvidenceRef).where(EvidenceRef.id == ev_id)
            )

        assert isinstance(stored_sr.id, UUID)
        assert stored_sr.workspace_id == workspace.id
        assert stored_sr.payload == {"full_name": "acme/repo", "private": True}
        assert stored_sr.payload_hash == "hash-" + marker
        assert stored_sr.is_deleted is False
        assert stored_repo.full_name == "acme/repo"
        assert stored_repo.visibility == REPOSITORY_VISIBILITY_PRIVATE
        assert stored_repo.repo_metadata == {"stars": 3}
        assert stored_pr.repository_id == repo_id
        assert stored_pr.state == PULL_REQUEST_STATE_OPEN
        assert stored_task.source_record_id == sr_id
        assert stored_task.due_date == date(2026, 7, 1)
        assert stored_ev.source_record_id == sr_id
        assert stored_ev.confidence == pytest.approx(0.9)
    finally:
        await _cleanup(marker)


async def test_source_record_unique_workspace_provider_external_id() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace = await _create_workspace(marker)
        async with AsyncSessionLocal() as session:
            for _ in range(2):
                session.add(
                    SourceRecord(
                        workspace_id=workspace.id,
                        provider=SOURCE_RECORD_PROVIDER_GITHUB,
                        external_id=f"dup-{marker}",
                        record_type="repository",
                        payload={},
                        payload_hash="h",
                        observed_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
                    )
                )
            with pytest.raises(
                IntegrityError,
                match="uq_source_records_workspace_provider_external_id",
            ):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


@pytest.mark.parametrize(
    ("model", "field", "value", "message"),
    [
        (SourceRecord, "provider", "slack", "ck_source_records_provider"),
        (Repository, "visibility", "secret", "ck_repositories_visibility"),
        (Task, "source_provider", "asana", "ck_tasks_source_provider"),
    ],
)
async def test_check_constraints_reject_unknown_values(
    model: type, field: str, value: str, message: str
) -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace = await _create_workspace(marker)
        base: dict = {"workspace_id": workspace.id}
        if model is SourceRecord:
            base.update(
                external_id=f"x-{marker}",
                record_type="repository",
                payload={},
                payload_hash="h",
                observed_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
                provider=SOURCE_RECORD_PROVIDER_GITHUB,
            )
        elif model is Repository:
            base.update(
                external_id=f"x-{marker}",
                name="r",
                full_name="acme/r",
                visibility=REPOSITORY_VISIBILITY_PRIVATE,
            )
        elif model is Task:
            base.update(title="t", source_provider=TASK_PROVIDER_GITHUB)
        base[field] = value

        async with AsyncSessionLocal() as session:
            session.add(model(**base))
            with pytest.raises(IntegrityError, match=message):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_pull_request_state_check_rejected() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace = await _create_workspace(marker)
        async with AsyncSessionLocal() as session:
            repository = Repository(
                workspace_id=workspace.id,
                external_id=f"repo-{marker}",
                name="repo",
                full_name="acme/repo",
            )
            session.add(repository)
            await session.flush()
            session.add(
                PullRequest(
                    workspace_id=workspace.id,
                    repository_id=repository.id,
                    external_id=f"pr-{marker}",
                    number=1,
                    title="bad state",
                    state="reopened",
                )
            )
            with pytest.raises(IntegrityError, match="ck_pull_requests_state"):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_evidence_ref_source_record_fk_enforced() -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    try:
        workspace = await _create_workspace(marker)
        async with AsyncSessionLocal() as session:
            session.add(
                EvidenceRef(
                    workspace_id=workspace.id,
                    source_record_id=uuid4(),
                )
            )
            with pytest.raises(
                IntegrityError, match="fk_evidence_refs_source_record_id"
            ):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_canonical_migration_tables_constraints_indexes_exist() -> None:
    async with AsyncSessionLocal() as session:
        tables = set(
            (
                await session.execute(
                    text(
                        """
                        select table_name from information_schema.tables
                        where table_schema = 'public'
                        and table_name in
                          ('source_records','evidence_refs','repositories','pull_requests','tasks')
                        """
                    )
                )
            ).scalars()
        )
        constraints = set(
            (
                await session.execute(
                    text(
                        """
                        select conname from pg_constraint
                        where conname in (
                          'ck_source_records_provider',
                          'uq_source_records_workspace_provider_external_id',
                          'fk_source_records_workspace_id',
                          'uq_repositories_workspace_provider_full_name',
                          'ck_repositories_visibility',
                          'ck_pull_requests_state',
                          'fk_pull_requests_repository_id',
                          'ck_tasks_source_provider',
                          'fk_evidence_refs_source_record_id'
                        )
                        """
                    )
                )
            ).scalars()
        )
        indexes = set(
            (
                await session.execute(
                    text(
                        """
                        select indexname from pg_indexes
                        where schemaname = 'public'
                        and indexname in (
                          'ix_source_records_workspace_record_type',
                          'ix_source_records_payload_hash',
                          'ix_tasks_workspace_status',
                          'ix_pull_requests_repository_id',
                          'ix_evidence_refs_source_record_id'
                        )
                        """
                    )
                )
            ).scalars()
        )

    assert tables == {
        "source_records",
        "evidence_refs",
        "repositories",
        "pull_requests",
        "tasks",
    }
    assert constraints == {
        "ck_source_records_provider",
        "uq_source_records_workspace_provider_external_id",
        "fk_source_records_workspace_id",
        "uq_repositories_workspace_provider_full_name",
        "ck_repositories_visibility",
        "ck_pull_requests_state",
        "fk_pull_requests_repository_id",
        "ck_tasks_source_provider",
        "fk_evidence_refs_source_record_id",
    }
    assert indexes == {
        "ix_source_records_workspace_record_type",
        "ix_source_records_payload_hash",
        "ix_tasks_workspace_status",
        "ix_pull_requests_repository_id",
        "ix_evidence_refs_source_record_id",
    }
