from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.connectors.github as github_connector
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import Membership, User, Workspace
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_JIRA,
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
        "owner_email": f"github-conn-{marker}{suffix}@example.test",
        "owner_name": "GitHub Connection Owner",
        "workspace_name": f"GitHub Connection {marker}{suffix}",
        "workspace_slug": f"github-conn-{marker}{suffix}",
    }


async def _cleanup_connection_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-conn-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-conn-{marker}%@example.test")
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


async def _seed_connection(
    workspace_id: str,
    *,
    provider: str = INTEGRATION_PROVIDER_GITHUB,
    status: str = INTEGRATION_CONNECTION_STATUS_CONNECTED,
    has_access_token: bool = True,
    has_refresh_token: bool = True,
    suffix: str = "primary",
) -> UUID:
    async with AsyncSessionLocal() as session:
        connection = IntegrationConnection(
            workspace_id=UUID(workspace_id),
            provider=provider,
            status=status,
            display_name=f"GitHub {suffix}",
            external_account_id=f"account-{suffix}",
            scopes=["repo:read", "user:read"],
            encrypted_access_token=(
                "encrypted-access-placeholder" if has_access_token else None
            ),
            encrypted_refresh_token=(
                "encrypted-refresh-placeholder" if has_refresh_token else None
            ),
            provider_metadata={
                "login": f"founderos-{suffix}",
                "access_token_hint": "must-not-leak",
                "nested": {
                    "safe": "kept",
                    "refresh_secret": "must-not-leak-nested",
                },
            },
        )
        session.add(connection)
        await session.commit()
        return connection.id


async def _count(model: type) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_github_connections_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connections_require_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections",
                headers=_headers(),
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connection_status_empty_workspace_is_local_bridge_only(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            list_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
            status_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert list_response.status_code == 200
        assert list_response.json() == {
            "connections": [],
            "count": 0,
            "provider": "github",
            "is_live": False,
            "warnings": [],
        }
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["status"] == "local_bridge_only"
        assert body["connection_id"] is None
        assert body["has_connection_record"] is False
        assert body["has_valid_token_record"] is False
        assert body["repository_read_available"] is True
        assert body["repository_read_source"] == "local_bridge"
        assert body["is_live"] is False
        assert any("local bridge only" in warning for warning in body["warnings"])
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connections_list_returns_only_github_and_redacts_tokens(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"], suffix="one")
        await _seed_connection(
            created["workspace"]["id"],
            provider=INTEGRATION_PROVIDER_JIRA,
            suffix="jira",
        )

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        connection = body["connections"][0]
        assert connection["id"] == str(connection_id)
        assert connection["provider"] == "github"
        assert connection["status"] == "connected"
        assert connection["has_access_token"] is True
        assert connection["has_refresh_token"] is True
        assert connection["metadata"] == {
            "login": "founderos-one",
            "nested": {"safe": "kept"},
        }
        assert "encrypted_access_token" not in response.text
        assert "encrypted_refresh_token" not in response.text
        assert "encrypted-access-placeholder" not in response.text
        assert "encrypted-refresh-placeholder" not in response.text
        assert "must-not-leak" not in response.text
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connection_detail_is_workspace_scoped_and_redacted(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)
    await _cleanup_connection_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        other = await _bootstrap_workspace(other_marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            wrong_owner = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
            )
            missing_connection = await client.get(
                f"/api/v1/workspaces/{other['workspace']['id']}/github/connections/{connection_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(other_marker)["owner_email"]},
            )
            allowed = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections/{connection_id}",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert wrong_owner.status_code == 404
        assert missing_connection.status_code == 404
        assert missing_connection.json() == {"detail": "github connection not found"}
        assert allowed.status_code == 200
        assert allowed.json()["id"] == str(connection_id)
        assert "encrypted-access-placeholder" not in allowed.text
    finally:
        await _cleanup_connection_fixture(marker)
        await _cleanup_connection_fixture(other_marker)


async def test_github_connection_status_connected_with_token(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        connection_id = await _seed_connection(created["workspace"]["id"])

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "connected"
        assert body["connection_id"] == str(connection_id)
        assert body["has_connection_record"] is True
        assert body["has_valid_token_record"] is True
        assert body["repository_read_source"] == "integration_connection"
        assert body["is_live"] is False
        assert body["warnings"] == []
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connection_status_warns_when_connected_record_has_no_token(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        await _seed_connection(
            created["workspace"]["id"],
            has_access_token=False,
            has_refresh_token=False,
        )

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "connected"
        assert body["has_valid_token_record"] is False
        assert body["repository_read_source"] == "local_bridge"
        assert any("no encrypted access token" in warning for warning in body["warnings"])
    finally:
        await _cleanup_connection_fixture(marker)


@pytest.mark.parametrize(
    "connection_status",
    [
        INTEGRATION_CONNECTION_STATUS_ERROR,
        INTEGRATION_CONNECTION_STATUS_REVOKED,
        INTEGRATION_CONNECTION_STATUS_DISABLED,
    ],
)
async def test_github_connection_status_maps_non_connected_statuses(
    monkeypatch,
    connection_status: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        await _seed_connection(created["workspace"]["id"], status=connection_status)

        async with _async_client() as client:
            response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == connection_status
        assert body["has_connection_record"] is True
        assert body["has_valid_token_record"] is False
        assert body["repository_read_source"] == "local_bridge"
        assert any(connection_status in warning for warning in body["warnings"])
    finally:
        await _cleanup_connection_fixture(marker)


async def test_github_connection_contract_makes_no_provider_call_or_sync_job(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_connection_fixture(marker)

    def fail_provider_call(*_args, **_kwargs):
        raise AssertionError("provider call should not be made")

    monkeypatch.setattr(
        github_connector,
        "fetch_org_repository_inventory_summary",
        fail_provider_call,
    )
    monkeypatch.setattr(github_connector, "list_repository_events", fail_provider_call)

    try:
        created = await _bootstrap_workspace(marker)
        await _seed_connection(created["workspace"]["id"])
        sync_job_count_before = await _count(SyncJob)

        async with _async_client() as client:
            list_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connections",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )
            status_response = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert list_response.status_code == 200
        assert status_response.status_code == 200
        assert await _count(SyncJob) == sync_job_count_before
    finally:
        await _cleanup_connection_fixture(marker)


def test_github_connection_contract_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("github_connection" in name for name in version_files)
