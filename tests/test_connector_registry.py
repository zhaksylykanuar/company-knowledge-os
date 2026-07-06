from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, Membership, User, Workspace
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    INTEGRATION_PROVIDER_GITHUB,
    INTEGRATION_PROVIDER_JIRA,
    IntegrationConnection,
)
from app.main import app
from app.services.connector_registry_service import build_workspace_connector_registry


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(marker: str) -> tuple[User, Workspace]:
    async with AsyncSessionLocal() as session:
        user = User(email=f"connectors-{marker}@example.test", name="Connector Owner")
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Connectors {marker}",
            slug=f"connectors-{marker}",
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
        await session.commit()
        return user, workspace


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"connectors-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"connectors-{marker}%@example.test")
                    )
                )
            ).scalars()
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
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def test_connector_registry_lists_mvp_connectors_without_secret_values() -> None:
    marker = uuid4().hex[:10]
    await _cleanup(marker)
    try:
        user, workspace = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    IntegrationConnection(
                        workspace_id=workspace.id,
                        provider=INTEGRATION_PROVIDER_GITHUB,
                        status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                        display_name="GitHub App",
                        external_account_id="github-org",
                        encrypted_access_token="SHOULD_NOT_LEAK_GITHUB_TOKEN",
                    ),
                    IntegrationConnection(
                        workspace_id=workspace.id,
                        provider=INTEGRATION_PROVIDER_JIRA,
                        status=INTEGRATION_CONNECTION_STATUS_ERROR,
                        display_name="Jira",
                        external_account_id="jira-site",
                        encrypted_access_token="SHOULD_NOT_LEAK_JIRA_TOKEN",
                    ),
                ]
            )
            await session.commit()

        async with AsyncSessionLocal() as session:
            registry = await build_workspace_connector_registry(
                session,
                workspace_id=workspace.id,
            )

        assert registry["workspace_id"] == str(workspace.id)
        assert registry["summary"] == {
            "available": 4,
            "connected": 1,
            "planned": 0,
            "total": 4,
        }
        assert registry["boundary"] == {
            "external_writes": False,
            "llm": False,
            "provider_calls": False,
            "reads_secrets": False,
        }
        by_provider = {connector["provider"]: connector for connector in registry["connectors"]}
        assert set(by_provider) == {"github", "jira", "gmail", "drive"}
        assert by_provider["github"]["status"] == "available"
        assert by_provider["github"]["manage_path"] == "/github"
        assert by_provider["github"]["connection_count"] == 1
        assert by_provider["github"]["connected_count"] == 1
        assert by_provider["jira"]["status"] == "available"
        assert by_provider["jira"]["manage_path"] == "/jira"
        assert by_provider["jira"]["connection_count"] == 1
        assert by_provider["jira"]["connected_count"] == 0
        assert by_provider["gmail"]["status"] == "available"
        assert by_provider["gmail"]["manage_path"] == "/gmail"
        assert by_provider["drive"]["status"] == "available"
        assert by_provider["drive"]["manage_path"] == "/drive"
        assert "SHOULD_NOT_LEAK" not in str(registry)
        assert user.email not in str(registry)

    finally:
        await _cleanup(marker)


async def test_connector_registry_api_requires_workspace_access_and_is_read_only(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:10]
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup(marker)
    await _cleanup(other_marker)
    try:
        user, workspace = await _seed_workspace(marker)
        other_user, _other_workspace = await _seed_workspace(other_marker)

        async with _client() as client:
            missing_owner = await client.get(
                f"/api/v1/workspaces/{workspace.id}/connectors",
                headers=_headers(),
            )
            wrong_owner = await client.get(
                f"/api/v1/workspaces/{workspace.id}/connectors",
                headers=_headers(),
                params={"owner_email": other_user.email},
            )
            allowed = await client.get(
                f"/api/v1/workspaces/{workspace.id}/connectors",
                headers=_headers(),
                params={"owner_email": user.email},
            )

        assert missing_owner.status_code == 403
        assert wrong_owner.status_code == 404
        assert allowed.status_code == 200
        body = allowed.json()
        assert body["summary"]["total"] == 4
        assert body["boundary"]["provider_calls"] is False
        assert body["boundary"]["external_writes"] is False
        assert {connector["provider"] for connector in body["connectors"]} == {
            "github",
            "jira",
            "gmail",
            "drive",
        }

    finally:
        await _cleanup(marker)
        await _cleanup(other_marker)
