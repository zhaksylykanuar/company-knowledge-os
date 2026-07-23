from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    IntegrationConnection,
)
from app.main import app
from app.services import connector_control_service
from app.services.connector_control_service import ProviderProbeResult
from app.services.secret_encryption import decrypt_secret

TEST_TOKEN = "connector-control-test-token"


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(
        settings,
        "secret_encryption_key",
        SecretStr("connector-control-encryption-key"),
    )
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(
    marker: str,
    *,
    member_role: str | None = None,
) -> tuple[User, Workspace, User | None]:
    async with AsyncSessionLocal() as session:
        owner = User(
            email=f"connector-control-{marker}@example.test",
            name="Connector Control Owner",
        )
        session.add(owner)
        await session.flush()
        workspace = Workspace(
            name=f"Connector Control {marker}",
            slug=f"connector-control-{marker}",
            created_by_user_id=owner.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=owner.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )
        )
        member = None
        if member_role is not None:
            member = User(
                email=f"connector-control-{marker}-{member_role}@example.test",
                name="Connector Control Member",
            )
            session.add(member)
            await session.flush()
            session.add(
                Membership(
                    workspace_id=workspace.id,
                    user_id=member.id,
                    role=member_role,
                )
            )
        await session.commit()
        return owner, workspace, member


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.scalars(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"connector-control-{marker}%")
                    )
                )
            ).all()
        )
        user_ids = list(
            (
                await session.scalars(
                    select(User.id).where(
                        User.email.like(
                            f"connector-control-{marker}%@example.test"
                        )
                    )
                )
            ).all()
        )
        if workspace_ids:
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
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


def _configuration_path(workspace_id: UUID, provider: str) -> str:
    return (
        f"/api/v1/workspaces/{workspace_id}/connectors/"
        f"{provider}/configuration"
    )


async def test_configuration_is_encrypted_and_control_center_never_returns_secret(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _ = await _seed_workspace(marker)
        payload = {
            "access_token": TEST_TOKEN,
            "account_email": owner.email,
            "auth_method": "jira_cloud_api_token",
            "base_url": "https://founderos-test.atlassian.net/",
            "display_name": "Company Jira",
            "scopes": ["read:jira-work", "read:jira-user"],
        }
        async with _client() as client:
            response = await client.post(
                _configuration_path(workspace.id, "jira"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json=payload,
            )
            center = await client.get(
                f"/api/v1/workspaces/{workspace.id}/connectors/control-center",
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "saved_unverified"
        assert response.json()["credential_present"] is True
        assert response.json()["base_url"] == "https://founderos-test.atlassian.net"
        assert TEST_TOKEN not in response.text
        assert "encrypted_access_token" not in response.text

        assert center.status_code == 200, center.text
        assert center.json()["boundary"] == {
            "external_writes": False,
            "provider_calls": False,
            "stored_secrets_returned": False,
            "write_checks_are_dry_run": True,
        }
        assert TEST_TOKEN not in center.text

        async with AsyncSessionLocal() as session:
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace.id,
                    IntegrationConnection.provider == "jira",
                )
            )
            assert connection is not None
            assert connection.status == INTEGRATION_CONNECTION_STATUS_DISABLED
            assert connection.encrypted_access_token is not None
            assert connection.encrypted_access_token.startswith("fernet:v1:")
            assert decrypt_secret(connection.encrypted_access_token) == TEST_TOKEN
            assert TEST_TOKEN not in str(connection.provider_metadata)
            assert connection.provider_metadata["created_via"] == "settings_integrations"
            assert (
                connection.provider_metadata["control_center"]["base_url"]
                == "https://founderos-test.atlassian.net"
            )
    finally:
        await _cleanup(marker)


async def test_configuration_rejects_unsafe_or_arbitrary_provider_urls(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace, _ = await _seed_workspace(marker)
        async with _client() as client:
            unsafe_jira = await client.post(
                _configuration_path(workspace.id, "jira"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json={
                    "access_token": TEST_TOKEN,
                    "account_email": owner.email,
                    "auth_method": "jira_cloud_api_token",
                    "base_url": "http://127.0.0.1:8000/internal",
                },
            )
            arbitrary_github = await client.post(
                _configuration_path(workspace.id, "github"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json={
                    "access_token": TEST_TOKEN,
                    "auth_method": "manual_provider_token",
                    "base_url": "https://github.example.test",
                },
            )

        assert unsafe_jira.status_code == 400
        assert "*.atlassian.net" in unsafe_jira.json()["detail"]
        assert arbitrary_github.status_code == 400
        assert arbitrary_github.json()["detail"] == (
            "custom provider URLs are not supported"
        )
        async with AsyncSessionLocal() as session:
            rows = (
                await session.scalars(
                    select(IntegrationConnection).where(
                        IntegrationConnection.workspace_id == workspace.id
                    )
                )
            ).all()
            assert rows == []
    finally:
        await _cleanup(marker)


async def test_read_check_uses_bounded_probe_and_write_check_is_dry_run(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_real_connectors", True)
    monkeypatch.setattr(settings, "enable_write_actions", True)
    monkeypatch.setattr(settings, "require_approval_for_writes", True)
    monkeypatch.setattr(settings, "github_write_allowed_repos", "qtwin-io/founderos")
    calls: list[str] = []

    async def _fake_probe(*args, **kwargs) -> ProviderProbeResult:
        calls.append(kwargs["provider"])
        return ProviderProbeResult(
            account_label="qtwin-io",
            records_visible=7,
            scopes=("repo", "read:org"),
        )

    monkeypatch.setattr(connector_control_service, "_probe_connection", _fake_probe)
    await _cleanup(marker)
    try:
        owner, workspace, _ = await _seed_workspace(marker)
        async with _client() as client:
            applied = await client.post(
                _configuration_path(workspace.id, "github"),
                headers=_headers(),
                params={"owner_email": owner.email},
                json={
                    "access_token": TEST_TOKEN,
                    "auth_method": "manual_provider_token",
                    "display_name": "GitHub fallback",
                    "scopes": ["repo"],
                },
            )
            read_check = await client.post(
                f"/api/v1/workspaces/{workspace.id}/connectors/github/checks/read",
                headers=_headers(),
                params={"owner_email": owner.email},
            )
            write_check = await client.post(
                f"/api/v1/workspaces/{workspace.id}/connectors/github/checks/write",
                headers=_headers(),
                params={"owner_email": owner.email},
            )

        assert applied.status_code == 200, applied.text
        assert read_check.status_code == 200, read_check.text
        assert read_check.json()["status"] == "passed"
        assert read_check.json()["records_visible"] == 7
        assert read_check.json()["external_write_performed"] is False
        assert calls == ["github"]

        assert write_check.status_code == 200, write_check.text
        assert write_check.json()["status"] == "ready"
        assert write_check.json()["provider_call_performed"] is False
        assert write_check.json()["external_write_performed"] is False
        assert write_check.json()["checks"] == {
            "approval_required": True,
            "credential_configured": True,
            "provider_write_supported": True,
            "read_verified": True,
            "target_allowlist_configured": True,
            "write_feature_enabled": True,
        }
        assert calls == ["github"]

        async with AsyncSessionLocal() as session:
            connection = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace.id,
                    IntegrationConnection.provider == "github",
                )
            )
            assert connection is not None
            assert connection.status == INTEGRATION_CONNECTION_STATUS_CONNECTED
            control = connection.provider_metadata["control_center"]
            assert control["read_check"]["status"] == "passed"
            assert control["write_check"]["external_write_performed"] is False
            assert TEST_TOKEN not in str(control)
    finally:
        await _cleanup(marker)


async def test_member_can_view_but_cannot_change_or_check_connectors(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        _, workspace, member = await _seed_workspace(
            marker,
            member_role=MEMBERSHIP_ROLE_MEMBER,
        )
        assert member is not None
        async with _client() as client:
            center = await client.get(
                f"/api/v1/workspaces/{workspace.id}/connectors/control-center",
                headers=_headers(),
                params={"owner_email": member.email},
            )
            apply_response = await client.post(
                _configuration_path(workspace.id, "github"),
                headers=_headers(),
                params={"owner_email": member.email},
                json={
                    "access_token": TEST_TOKEN,
                    "auth_method": "manual_provider_token",
                },
            )
            check_response = await client.post(
                f"/api/v1/workspaces/{workspace.id}/connectors/github/checks/write",
                headers=_headers(),
                params={"owner_email": member.email},
            )

        assert center.status_code == 200
        assert apply_response.status_code == 403
        assert check_response.status_code == 403
        assert apply_response.json() == {"detail": "insufficient workspace role"}
    finally:
        await _cleanup(marker)


async def test_managed_github_probe_reads_only_one_bounded_repository_page(
    monkeypatch,
) -> None:
    observed: dict[str, object] = {}

    async def _fake_signing_credential(*args, **kwargs):
        return SimpleNamespace(app_id="123", private_key_pem="not-used")

    async def _fake_mint(*args, **kwargs):
        observed["installation_id"] = kwargs["installation_id"]
        return SimpleNamespace(token="temporary-jit-token")

    async def _fake_get_json(url: str, *, headers, auth=None):
        observed["url"] = url
        observed["authorization_present"] = bool(headers.get("Authorization"))
        return {"repositories": [{"id": 1}], "total_count": 321}, {}

    monkeypatch.setattr(
        connector_control_service,
        "get_github_app_signing_credential",
        _fake_signing_credential,
    )
    monkeypatch.setattr(
        connector_control_service,
        "mint_installation_access_token",
        _fake_mint,
    )
    monkeypatch.setattr(connector_control_service, "_get_json", _fake_get_json)

    result = await connector_control_service._probe_managed_github(
        None,  # type: ignore[arg-type]
        workspace_id=uuid4(),
        installation=SimpleNamespace(
            account_login="qtwin-io",
            installation_id="456",
            permissions={"contents": "read"},
        ),
    )

    assert observed == {
        "authorization_present": True,
        "installation_id": "456",
        "url": (
            "https://api.github.com/installation/repositories?"
            "per_page=1&page=1"
        ),
    }
    assert result.account_label == "qtwin-io"
    assert result.records_visible == 321
    assert result.scopes == ("contents",)
