from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)


async def _cleanup_integration_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = (
            await session.execute(
                select(Workspace.id).where(Workspace.slug.like(f"integration-{marker}%"))
            )
        ).scalars()
        user_ids = (
            await session.execute(
                select(User.id).where(
                    User.email.like(f"integration-{marker}%@example.test")
                )
            )
        ).scalars()
        workspace_id_values = list(workspace_ids)
        user_id_values = list(user_ids)
        connection_ids: list[UUID] = []

        if workspace_id_values:
            connection_ids = list(
                (
                    await session.execute(
                        select(IntegrationConnection.id).where(
                            IntegrationConnection.workspace_id.in_(workspace_id_values)
                        )
                    )
                ).scalars()
            )
            await session.execute(
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_id_values))
            )
        if connection_ids:
            await session.execute(
                delete(SyncJob).where(SyncJob.connection_id.in_(connection_ids))
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.id.in_(connection_ids)
                )
            )
        if workspace_id_values:
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_id_values))
            )
        if user_id_values:
            await session.execute(
                delete(Membership).where(Membership.user_id.in_(user_id_values))
            )
        if workspace_id_values:
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_id_values))
            )
        if user_id_values:
            await session.execute(delete(User).where(User.id.in_(user_id_values)))
        await session.commit()


async def _create_identity_fixture(marker: str) -> tuple[User, Workspace, Membership]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"integration-{marker}@example.test",
            name="Integration Owner",
        )
        session.add(user)
        await session.flush()

        workspace = Workspace(
            name="Integration Workspace",
            slug=f"integration-{marker}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()

        membership = Membership(
            workspace_id=workspace.id,
            user_id=user.id,
            role=MEMBERSHIP_ROLE_OWNER,
        )
        session.add(membership)
        await session.commit()

    return user, workspace, membership


def test_integration_models_register_with_metadata() -> None:
    assert IntegrationConnection.__tablename__ == "integration_connections"
    assert SyncJob.__tablename__ == "sync_jobs"
    assert IntegrationConnection.__table__.c.metadata.name == "metadata"


async def test_create_identity_connection_and_sync_job() -> None:
    marker = uuid4().hex
    await _cleanup_integration_fixture(marker)

    try:
        user, workspace, membership = await _create_identity_fixture(marker)

        async with AsyncSessionLocal() as session:
            connection = IntegrationConnection(
                workspace_id=workspace.id,
                provider=INTEGRATION_PROVIDER_GITHUB,
                display_name="GitHub FounderOS",
                external_account_id=f"github-account-{marker}",
                scopes=["repo:read", "user:read"],
                encrypted_access_token="ciphertext-access-placeholder",
                encrypted_refresh_token="ciphertext-refresh-placeholder",
                provider_metadata={"login": f"founderos-{marker}"},
            )
            session.add(connection)
            await session.flush()

            job = SyncJob(
                workspace_id=workspace.id,
                connection_id=connection.id,
                provider=INTEGRATION_PROVIDER_GITHUB,
                cursor_before={"cursor": "before"},
                cursor_after={"cursor": "after"},
            )
            session.add(job)
            await session.commit()

        async with AsyncSessionLocal() as session:
            stored_connection = await session.scalar(
                select(IntegrationConnection).where(IntegrationConnection.id == connection.id)
            )
            stored_job = await session.scalar(select(SyncJob).where(SyncJob.id == job.id))

        assert isinstance(user.id, UUID)
        assert isinstance(workspace.id, UUID)
        assert isinstance(membership.id, UUID)
        assert stored_connection.workspace_id == workspace.id
        assert stored_connection.provider == INTEGRATION_PROVIDER_GITHUB
        assert stored_connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
        assert stored_connection.scopes == ["repo:read", "user:read"]
        assert stored_connection.provider_metadata == {"login": f"founderos-{marker}"}
        assert stored_job.workspace_id == workspace.id
        assert stored_job.connection_id == stored_connection.id
        assert stored_job.provider == INTEGRATION_PROVIDER_GITHUB
        assert stored_job.status == SYNC_JOB_STATUS_QUEUED
        assert stored_job.sync_type == SYNC_JOB_TYPE_MANUAL
        assert stored_job.records_seen == 0
        assert stored_job.records_created == 0
        assert stored_job.records_updated == 0

    finally:
        await _cleanup_integration_fixture(marker)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", "slack", "ck_integration_connections_provider"),
        ("status", "syncing", "ck_integration_connections_status"),
    ],
)
async def test_integration_connection_rejects_unknown_values(
    field: str, value: str, message: str
) -> None:
    marker = uuid4().hex
    await _cleanup_integration_fixture(marker)

    try:
        _, workspace, _ = await _create_identity_fixture(marker)

        async with AsyncSessionLocal() as session:
            connection_values = {
                "workspace_id": workspace.id,
                "provider": INTEGRATION_PROVIDER_GITHUB,
            }
            connection_values[field] = value
            session.add(IntegrationConnection(**connection_values))

            with pytest.raises(IntegrityError, match=message):
                await session.commit()
            await session.rollback()

    finally:
        await _cleanup_integration_fixture(marker)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", "slack", "ck_sync_jobs_provider"),
        ("status", "cancelled", "ck_sync_jobs_status"),
        ("sync_type", "scheduled", "ck_sync_jobs_sync_type"),
    ],
)
async def test_sync_job_rejects_unknown_values(
    field: str, value: str, message: str
) -> None:
    marker = uuid4().hex
    await _cleanup_integration_fixture(marker)

    try:
        _, workspace, _ = await _create_identity_fixture(marker)

        async with AsyncSessionLocal() as session:
            connection = IntegrationConnection(
                workspace_id=workspace.id,
                provider=INTEGRATION_PROVIDER_GITHUB,
            )
            session.add(connection)
            await session.flush()

            job_values = {
                "workspace_id": workspace.id,
                "connection_id": connection.id,
                "provider": INTEGRATION_PROVIDER_GITHUB,
            }
            job_values[field] = value
            session.add(SyncJob(**job_values))

            with pytest.raises(IntegrityError, match=message):
                await session.commit()
            await session.rollback()

    finally:
        await _cleanup_integration_fixture(marker)


async def test_integration_connection_workspace_fk_is_enforced() -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            IntegrationConnection(
                workspace_id=uuid4(),
                provider=INTEGRATION_PROVIDER_GITHUB,
            )
        )

        with pytest.raises(IntegrityError, match="fk_integration_connections_workspace_id"):
            await session.commit()
        await session.rollback()


async def test_sync_job_connection_fk_is_enforced() -> None:
    marker = uuid4().hex
    await _cleanup_integration_fixture(marker)

    try:
        _, workspace, _ = await _create_identity_fixture(marker)

        async with AsyncSessionLocal() as session:
            session.add(
                SyncJob(
                    workspace_id=workspace.id,
                    connection_id=uuid4(),
                    provider=INTEGRATION_PROVIDER_GITHUB,
                )
            )

            with pytest.raises(IntegrityError, match="fk_sync_jobs_connection_id"):
                await session.commit()
            await session.rollback()

    finally:
        await _cleanup_integration_fixture(marker)


async def test_connection_sync_migration_tables_indexes_constraints_exist() -> None:
    async with AsyncSessionLocal() as session:
        tables = (
            await session.execute(
                text(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public'
                    and table_name in ('integration_connections', 'sync_jobs')
                    """
                )
            )
        ).scalars()
        constraints = (
            await session.execute(
                text(
                    """
                    select conname
                    from pg_constraint
                    where conname in (
                        'ck_integration_connections_provider',
                        'ck_integration_connections_status',
                        'fk_integration_connections_workspace_id',
                        'ck_sync_jobs_provider',
                        'ck_sync_jobs_status',
                        'ck_sync_jobs_sync_type',
                        'fk_sync_jobs_connection_id',
                        'fk_sync_jobs_workspace_id'
                    )
                    """
                )
            )
        ).scalars()
        indexes = (
            await session.execute(
                text(
                    """
                    select indexname
                    from pg_indexes
                    where schemaname = 'public'
                    and tablename in ('integration_connections', 'sync_jobs')
                    and indexname in (
                        'ix_integration_connections_workspace_provider',
                        'ix_integration_connections_provider_external_account_id',
                        'ix_sync_jobs_workspace_status',
                        'ix_sync_jobs_connection_started_at'
                    )
                    """
                )
            )
        ).scalars()

    assert set(tables) == {"integration_connections", "sync_jobs"}
    assert set(constraints) == {
        "ck_integration_connections_provider",
        "ck_integration_connections_status",
        "fk_integration_connections_workspace_id",
        "ck_sync_jobs_provider",
        "ck_sync_jobs_status",
        "ck_sync_jobs_sync_type",
        "fk_sync_jobs_connection_id",
        "fk_sync_jobs_workspace_id",
    }
    assert set(indexes) == {
        "ix_integration_connections_workspace_provider",
        "ix_integration_connections_provider_external_account_id",
        "ix_sync_jobs_workspace_status",
        "ix_sync_jobs_connection_started_at",
    }
