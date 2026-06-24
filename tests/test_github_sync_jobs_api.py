from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.event_models import SourceEvent
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_JIRA,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_TYPE_MANUAL,
    IntegrationConnection,
    SyncJob,
)
from app.main import app


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"github-sync-{marker}{suffix}@example.test",
        "owner_name": "GitHub Sync Owner",
        "workspace_name": f"GitHub Sync {marker}{suffix}",
        "workspace_slug": f"github-sync-{marker}{suffix}",
    }


async def _cleanup_sync_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-sync-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-sync-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _bootstrap_workspace(marker: str, *, suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker, suffix=suffix),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_workspace_user(
    workspace_id: str,
    marker: str,
    *,
    role: str,
    suffix: str,
) -> str:
    email = f"github-sync-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"GitHub Sync {role}")
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                workspace_id=UUID(workspace_id),
                user_id=user.id,
                role=role,
            )
        )
        await session.commit()
    return email


async def _seed_connection(
    workspace_id: str,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    status: str = INTEGRATION_CONNECTION_STATUS_CONNECTED,
    suffix: str = "primary",
) -> UUID:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=provider,
            status=status,
            display_name=f"GitHub Sync {suffix}",
            external_account_id=f"sync-account-{suffix}",
            scopes=["repo:read"],
            encrypted_access_token="encrypted-access-placeholder",
            provider_metadata={"login": f"founderos-sync-{suffix}"},
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _seed_sync_job(
    workspace_id: str,
    connection_id: UUID,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    suffix: str = "primary",
) -> UUID:
    async with AsyncSessionLocal() as session:
        sync_job = SyncJob(
            workspace_id=UUID(workspace_id),
            connection_id=connection_id,
            provider=provider,
            status=SYNC_JOB_STATUS_QUEUED,
            sync_type=SYNC_JOB_TYPE_MANUAL,
            logs=[{"note": f"seeded {suffix}", "execution_started": False}],
        )
        session.add(sync_job)
        await session.commit()
        return sync_job.id


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def _stored_sync_job(sync_job_id: str) -> SyncJob:
    async with AsyncSessionLocal() as session:
        sync_job = await session.scalar(
            select(SyncJob).where(SyncJob.id == UUID(sync_job_id))
        )
        assert sync_job is not None
        return sync_job


async def test_create_github_sync_job_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text
    finally:
        await _cleanup_sync_fixture(marker)


async def test_create_github_sync_job_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                json={"sync_type": "manual"},
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_sync_fixture(marker)


async def test_owner_can_create_manual_github_sync_job(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={
                    "sync_type": "manual",
                    "cursor_before": {"since": "2026-06-01T00:00:00Z"},
                    "notes": "manual local sync record",
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["is_live"] is False
        assert body["execution_started"] is False
        assert any("no GitHub sync execution" in warning for warning in body["warnings"])
        sync_job = body["sync_job"]
        assert sync_job["workspace_id"] == created["workspace"]["id"]
        assert sync_job["connection_id"] == str(connection_id)
        assert sync_job["provider"] == "github"
        assert sync_job["status"] == "queued"
        assert sync_job["sync_type"] == "manual"
        assert sync_job["records_seen"] == 0
        assert sync_job["records_created"] == 0
        assert sync_job["records_updated"] == 0
        assert sync_job["started_at"] is None
        assert sync_job["finished_at"] is None
        assert sync_job["cursor_before"] == {"since": "2026-06-01T00:00:00Z"}
        assert sync_job["cursor_after"] is None
        assert sync_job["is_live"] is False
        assert sync_job["execution_started"] is False
        assert sync_job["logs"]["events"][0]["requested_by"] == "operator_api_key"
        assert sync_job["logs"]["events"][0]["execution_started"] is False
        assert sync_job["logs"]["events"][0]["notes"] == "manual local sync record"

        stored = await _stored_sync_job(sync_job["id"])
        assert stored.provider == INTEGRATION_PROVIDER_GITHUB
        assert stored.status == SYNC_JOB_STATUS_QUEUED
        assert stored.sync_type == SYNC_JOB_TYPE_MANUAL
        assert stored.records_seen == 0
        assert stored.started_at is None
        assert stored.finished_at is None
    finally:
        await _cleanup_sync_fixture(marker)


async def test_admin_can_create_manual_github_sync_job(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        admin_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_ADMIN,
            suffix="admin",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": admin_email},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 201
        assert response.json()["sync_job"]["status"] == "queued"
    finally:
        await _cleanup_sync_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_and_viewer_cannot_create_manual_github_sync_job(
    monkeypatch,
    role: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        user_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": user_email},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_sync_fixture(marker)


async def test_create_github_sync_job_rejects_non_github_connection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(
            created["workspace"]["id"],
            provider=INTEGRATION_PROVIDER_JIRA,
            suffix="jira",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 404
        assert response.json() == {"detail": "github connection not found"}
    finally:
        await _cleanup_sync_fixture(marker)


async def test_create_github_sync_job_rejects_unknown_connection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{uuid4()}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 404
        assert response.json() == {"detail": "github connection not found"}
    finally:
        await _cleanup_sync_fixture(marker)


@pytest.mark.parametrize(
    "connection_status",
    [
        INTEGRATION_CONNECTION_STATUS_ERROR,
        INTEGRATION_CONNECTION_STATUS_REVOKED,
        INTEGRATION_CONNECTION_STATUS_DISABLED,
    ],
)
async def test_create_github_sync_job_rejects_non_connected_connection(
    monkeypatch,
    connection_status: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(
            created["workspace"]["id"],
            status=connection_status,
        )

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "github connection must be connected"}
    finally:
        await _cleanup_sync_fixture(marker)


async def test_create_github_sync_job_rejects_non_manual_sync_type(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_count_before = await _count(SyncJob)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "initial"},
            )

        assert response.status_code == 422
        assert await _count(SyncJob) == sync_job_count_before
    finally:
        await _cleanup_sync_fixture(marker)


async def test_create_github_sync_job_does_not_call_live_or_source_paths(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)


    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        source_event_count_before = await _count(SourceEvent)
        sync_job_count_before = await _count(SyncJob)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={"sync_type": "manual"},
            )

        assert response.status_code == 201
        assert response.json()["sync_job"]["execution_started"] is False
        assert await _count(SourceEvent) == source_event_count_before
        assert await _count(SyncJob) == sync_job_count_before + 1
    finally:
        await _cleanup_sync_fixture(marker)


async def test_list_github_sync_jobs_returns_only_workspace_github_jobs(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)
    await _cleanup_sync_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        connection_id = await _seed_connection(created["workspace"]["id"], suffix="one")
        jira_connection_id = await _seed_connection(
            created["workspace"]["id"],
            provider=INTEGRATION_PROVIDER_JIRA,
            suffix="jira",
        )
        other_connection_id = await _seed_connection(
            other["workspace"]["id"],
            suffix="other",
        )
        expected_sync_job_id = await _seed_sync_job(
            created["workspace"]["id"],
            connection_id,
            suffix="expected",
        )
        await _seed_sync_job(
            created["workspace"]["id"],
            jira_connection_id,
            provider=INTEGRATION_PROVIDER_JIRA,
            suffix="jira",
        )
        await _seed_sync_job(
            other["workspace"]["id"],
            other_connection_id,
            suffix="other",
        )

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["provider"] == "github"
        assert body["is_live"] is False
        assert body["warnings"] == []
        assert body["sync_jobs"][0]["id"] == str(expected_sync_job_id)
        assert body["sync_jobs"][0]["provider"] == "github"
    finally:
        await _cleanup_sync_fixture(marker)
        await _cleanup_sync_fixture(other_marker)


async def test_sync_job_detail_requires_workspace_access_and_scope(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)
    await _cleanup_sync_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            missing_owner_context = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}",
                headers=_headers(),
            )
            wrong_owner = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
            )
            cross_workspace = await client.get(
                f"/api/v1/workspaces/{other['workspace']['id']}/github/sync-jobs/{sync_job_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
            )
            allowed = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert missing_owner_context.status_code == 403
        assert wrong_owner.status_code == 404
        assert cross_workspace.status_code == 404
        assert cross_workspace.json() == {"detail": "github sync job not found"}
        assert allowed.status_code == 200
        body = allowed.json()
        assert body["id"] == str(sync_job_id)
        assert body["workspace_id"] == created["workspace"]["id"]
        assert body["provider"] == "github"
        assert body["is_live"] is False
        assert body["execution_started"] is False
        assert any("no GitHub sync execution" in warning for warning in body["warnings"])
    finally:
        await _cleanup_sync_fixture(marker)
        await _cleanup_sync_fixture(other_marker)


async def test_viewer_can_read_github_sync_jobs(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_sync_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        viewer_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_VIEWER,
            suffix="viewer-read",
        )
        connection_id = await _seed_connection(created["workspace"]["id"])
        sync_job_id = await _seed_sync_job(created["workspace"]["id"], connection_id)

        async with _async_client() as client:
            list_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs",
                headers=_headers(),
                params={"owner_email": viewer_email},
            )
            detail_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/sync-jobs/{sync_job_id}",
                headers=_headers(),
                params={"owner_email": viewer_email},
            )

        assert list_response.status_code == 200
        assert detail_response.status_code == 200
        assert list_response.json()["count"] == 1
        assert detail_response.json()["id"] == str(sync_job_id)
    finally:
        await _cleanup_sync_fixture(marker)


def test_github_sync_job_api_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("github_sync_job" in name for name in version_files)
    assert not any("manual_sync_job" in name for name in version_files)
