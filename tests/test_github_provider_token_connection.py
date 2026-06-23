from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

import app.connectors.github as github_connector
from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_PROVIDER_GITHUB,
    IntegrationConnection,
    SyncJob,
)
from app.main import app
from app.services.secret_encryption import decrypt_secret, encrypt_secret

PLAIN_TEST_TOKEN = "plain-test-token-value"
UPDATED_TEST_TOKEN = "updated-plain-test-token-value"


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "secret_encryption_key", SecretStr("test-encryption-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _bootstrap_payload(marker: str, *, suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"github-token-{marker}{suffix}@example.test",
        "owner_name": "GitHub Token Owner",
        "workspace_name": f"GitHub Token {marker}{suffix}",
        "workspace_slug": f"github-token-{marker}{suffix}",
    }


def _provider_token_payload(
    *,
    access_token: str = PLAIN_TEST_TOKEN,
    external_account_id: str = "qtwin-io",
) -> dict:
    return {
        "display_name": "GitHub manual connection",
        "external_account_id": external_account_id,
        "access_token": access_token,
        "scopes": ["repo", "read:org", "repo"],
        "metadata": {
            "note": "manual MVP bridge",
            "access_token_hint": access_token,
            "nested": {
                "safe": "kept",
                "secret_value": "must-not-store",
            },
        },
    }


async def _cleanup_provider_token_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"github-token-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"github-token-{marker}%@example.test")
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
            "/v1/workspaces/bootstrap",
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
    email = f"github-token-{marker}-{suffix}@example.test"
    async with AsyncSessionLocal() as session:
        user = User(email=email, name=f"GitHub Token {role}")
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


async def _connection_count(workspace_id: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(IntegrationConnection)
                .where(IntegrationConnection.workspace_id == UUID(workspace_id))
                .where(IntegrationConnection.provider == INTEGRATION_PROVIDER_GITHUB)
            )
            or 0
        )


async def _sync_job_count() -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(SyncJob)) or 0)


async def _stored_connection(connection_id: str) -> IntegrationConnection:
    async with AsyncSessionLocal() as session:
        connection = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.id == UUID(connection_id)
            )
        )
        assert connection is not None
        return connection


def test_secret_encryption_roundtrip(monkeypatch) -> None:
    _set_auth(monkeypatch)

    encrypted = encrypt_secret(PLAIN_TEST_TOKEN)

    assert encrypted != PLAIN_TEST_TOKEN
    assert encrypted.startswith("fernet:v1:")
    assert decrypt_secret(encrypted) == PLAIN_TEST_TOKEN


async def test_provider_token_endpoint_requires_api_key(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=_provider_token_payload(),
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_provider_token_endpoint_requires_owner_email_context(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                json=_provider_token_payload(),
            )

        assert response.status_code == 403
        assert response.json() == {
            "detail": "owner_email is required for operator workspace access"
        }
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_owner_can_create_provider_token_connection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=_provider_token_payload(),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["is_live"] is False
        assert any("not validated with GitHub" in warning for warning in body["warnings"])
        connection = body["connection"]
        assert connection["provider"] == "github"
        assert connection["status"] == "connected"
        assert connection["display_name"] == "GitHub manual connection"
        assert connection["external_account_id"] == "qtwin-io"
        assert connection["scopes"] == ["repo", "read:org"]
        assert connection["has_access_token"] is True
        assert connection["has_refresh_token"] is False
        assert connection["metadata"]["connection_method"] == "manual_provider_token"
        assert connection["metadata"]["token_validated"] is False
        assert connection["metadata"]["created_via"] == "founderos_operator_bridge"
        assert connection["metadata"]["user_metadata"] == {
            "note": "manual MVP bridge",
            "nested": {"safe": "kept"},
        }
        assert "encrypted_access_token" not in response.text
        assert "encrypted_refresh_token" not in response.text
        assert PLAIN_TEST_TOKEN not in response.text

        stored = await _stored_connection(connection["id"])
        assert stored.encrypted_access_token is not None
        assert stored.encrypted_access_token != PLAIN_TEST_TOKEN
        assert decrypt_secret(stored.encrypted_access_token) == PLAIN_TEST_TOKEN
        assert stored.encrypted_refresh_token is None
        assert PLAIN_TEST_TOKEN not in json.dumps(stored.provider_metadata)
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_admin_can_create_provider_token_connection(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        admin_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=MEMBERSHIP_ROLE_ADMIN,
            suffix="admin",
        )

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": admin_email},
                json=_provider_token_payload(external_account_id="admin-org"),
            )

        assert response.status_code == 200
        assert response.json()["connection"]["external_account_id"] == "admin-org"
    finally:
        await _cleanup_provider_token_fixture(marker)


@pytest.mark.parametrize("role", [MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER])
async def test_member_and_viewer_cannot_create_provider_token_connection(
    monkeypatch,
    role: str,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        user_email = await _add_workspace_user(
            created["workspace"]["id"],
            marker,
            role=role,
            suffix=role,
        )

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": user_email},
                json=_provider_token_payload(external_account_id=f"{role}-org"),
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_provider_token_endpoint_rejects_empty_access_token(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json={**_provider_token_payload(), "access_token": "   "},
            )

        assert response.status_code == 422
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_provider_token_repeated_external_account_updates_existing_connection(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        url = f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token"
        params = {"owner_email": _bootstrap_payload(marker)["owner_email"]}

        async with _async_client() as client:
            first = await client.post(
                url,
                headers=_headers(),
                params=params,
                json=_provider_token_payload(external_account_id="same-org"),
            )
            second = await client.post(
                url,
                headers=_headers(),
                params=params,
                json={
                    **_provider_token_payload(
                        access_token=UPDATED_TEST_TOKEN,
                        external_account_id="same-org",
                    ),
                    "display_name": "Updated GitHub connection",
                    "scopes": ["read:org"],
                    "metadata": {"note": "updated"},
                },
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["connection"]["id"] == second.json()["connection"]["id"]
        assert second.json()["connection"]["display_name"] == "Updated GitHub connection"
        assert second.json()["connection"]["scopes"] == ["read:org"]
        assert await _connection_count(created["workspace"]["id"]) == 1

        stored = await _stored_connection(second.json()["connection"]["id"])
        assert decrypt_secret(stored.encrypted_access_token or "") == UPDATED_TEST_TOKEN
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_connection_status_is_connected_after_provider_token_connection(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            create_response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=_provider_token_payload(),
            )
            status_response = await client.get(
                f"/v1/workspaces/{created['workspace']['id']}/github/connection-status",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
            )

        assert create_response.status_code == 200
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["status"] == "connected"
        assert body["connection_id"] == create_response.json()["connection"]["id"]
        assert body["has_valid_token_record"] is True
        assert body["repository_read_source"] == "integration_connection"
        assert body["is_live"] is False
    finally:
        await _cleanup_provider_token_fixture(marker)


async def test_provider_token_connection_makes_no_provider_call_or_sync_job(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_provider_token_fixture(marker)

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
        sync_job_count_before = await _sync_job_count()

        async with _async_client() as client:
            response = await client.post(
                f"/v1/workspaces/{created['workspace']['id']}/github/connections/provider-token",
                headers=_headers(),
                params={"owner_email": _bootstrap_payload(marker)["owner_email"]},
                json=_provider_token_payload(),
            )

        assert response.status_code == 200
        assert await _sync_job_count() == sync_job_count_before
    finally:
        await _cleanup_provider_token_fixture(marker)


def test_provider_token_connection_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert not any("provider_token" in name for name in version_files)
