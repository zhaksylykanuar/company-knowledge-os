from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.api.auth import API_AUTH_FAILURE_DETAIL, settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    USER_STATUS_DISABLED,
    Membership,
    User,
    Workspace,
)
from app.main import app
from app.services.identity_service import (
    IdentityAccessError,
    ensure_role_allows,
    role_allows,
)


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", enabled)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _bootstrap_payload(marker: str, *, slug_suffix: str = "") -> dict[str, str]:
    return {
        "owner_email": f"workspace-{marker}@example.test",
        "owner_name": "Workspace Owner",
        "workspace_name": f"Workspace {marker}{slug_suffix}",
        "workspace_slug": f"workspace-{marker}{slug_suffix}",
    }


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _cleanup_workspace_contract_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"workspace-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"workspace-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(
                delete(Membership).where(Membership.user_id.in_(user_ids))
            )
        if workspace_ids:
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _bootstrap_workspace(marker: str, *, slug_suffix: str = "") -> dict:
    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json=_bootstrap_payload(marker, slug_suffix=slug_suffix),
        )
    assert response.status_code == 201, response.text
    return response.json()


async def test_bootstrap_endpoint_creates_user_workspace_membership(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        body = await _bootstrap_workspace(marker)

        assert body["user"]["email"] == f"workspace-{marker}@example.test"
        assert body["user"]["name"] == "Workspace Owner"
        assert body["user"]["status"] == "active"
        assert body["workspace"]["slug"] == f"workspace-{marker}"
        assert body["workspace"]["status"] == "active"
        assert body["membership"]["role"] == MEMBERSHIP_ROLE_OWNER

        async with AsyncSessionLocal() as session:
            user = await session.scalar(
                select(User).where(User.email == f"workspace-{marker}@example.test")
            )
            workspace = await session.scalar(
                select(Workspace).where(Workspace.slug == f"workspace-{marker}")
            )
            membership = await session.scalar(
                select(Membership)
                .where(Membership.user_id == user.id)
                .where(Membership.workspace_id == workspace.id)
            )

        assert user is not None
        assert workspace is not None
        assert membership is not None
        assert membership.role == MEMBERSHIP_ROLE_OWNER

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_bootstrap_reuses_existing_user_by_email(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        first = await _bootstrap_workspace(marker, slug_suffix="-one")
        second = await _bootstrap_workspace(marker, slug_suffix="-two")

        assert second["user"]["id"] == first["user"]["id"]
        assert second["workspace"]["id"] != first["workspace"]["id"]
        assert second["membership"]["role"] == MEMBERSHIP_ROLE_OWNER

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_bootstrap_rejects_duplicate_workspace_slug(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                "/api/v1/workspaces/bootstrap",
                headers=_headers(),
                json=_bootstrap_payload(marker),
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "workspace slug already exists"}

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_list_returns_owner_workspaces(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.get(
                "/api/v1/workspaces",
                headers=_headers(),
                params={"owner_email": f"workspace-{marker}@example.test"},
            )

        assert response.status_code == 200
        assert created["workspace"]["slug"] in {
            workspace["slug"] for workspace in response.json()["workspaces"]
        }

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_detail_requires_membership_access(monkeypatch) -> None:
    marker = uuid4().hex
    other_marker = f"{marker}-other"
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)
    await _cleanup_workspace_contract_fixture(other_marker)

    try:
        created = await _bootstrap_workspace(marker)
        await _bootstrap_workspace(other_marker)

        async with _async_client() as client:
            missing_owner_context = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}",
                headers=_headers(),
            )
            wrong_owner = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}",
                headers=_headers(),
                params={"owner_email": f"workspace-{other_marker}@example.test"},
            )
            allowed = await client.get(
                f"/api/v1/workspaces/{created['workspace']['id']}",
                headers=_headers(),
                params={"owner_email": f"workspace-{marker}@example.test"},
            )

        assert missing_owner_context.status_code == 403
        assert wrong_owner.status_code == 404
        assert allowed.status_code == 200
        assert allowed.json()["workspace"]["id"] == created["workspace"]["id"]

    finally:
        await _cleanup_workspace_contract_fixture(marker)
        await _cleanup_workspace_contract_fixture(other_marker)


async def test_workspace_members_can_be_listed_and_provisioned_locally(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = f"workspace-{marker}@example.test"
        teammate_email = f"workspace-{marker}-teammate@example.test"

        async with _async_client() as client:
            before = await client.get(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
            )
            provisioned = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "email": teammate_email,
                    "name": "Teammate",
                    "role": MEMBERSHIP_ROLE_MEMBER,
                },
            )
            after = await client.get(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
            )

        assert before.status_code == 200
        assert [member["membership"]["role"] for member in before.json()["members"]] == [
            MEMBERSHIP_ROLE_OWNER
        ]

        assert provisioned.status_code == 201, provisioned.text
        body = provisioned.json()
        assert body["member"]["user"]["email"] == teammate_email
        assert body["member"]["user"]["name"] == "Teammate"
        assert body["member"]["membership"]["role"] == MEMBERSHIP_ROLE_MEMBER
        assert body["external_invite_sent"] is False
        assert body["provider_write_performed"] is False
        assert "external provider write" in body["warnings"][0]

        assert after.status_code == 200
        members = after.json()["members"]
        assert {member["user"]["email"] for member in members} == {
            owner_email,
            teammate_email,
        }

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_member_provisioning_rejects_duplicate_membership(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = f"workspace-{marker}@example.test"
        teammate_email = f"workspace-{marker}-duplicate@example.test"
        payload = {
            "email": teammate_email,
            "name": "Duplicate",
            "role": MEMBERSHIP_ROLE_VIEWER,
        }

        async with _async_client() as client:
            first = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=payload,
            )
            duplicate = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
                json=payload,
            )

        assert first.status_code == 201, first.text
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "workspace membership already exists"}

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_member_provisioning_requires_admin_role(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = f"workspace-{marker}@example.test"
        viewer_email = f"workspace-{marker}-viewer@example.test"

        async with _async_client() as client:
            viewer = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "email": viewer_email,
                    "name": "Viewer",
                    "role": MEMBERSHIP_ROLE_VIEWER,
                },
            )
            forbidden = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": viewer_email},
                json={
                    "email": f"workspace-{marker}-other@example.test",
                    "role": MEMBERSHIP_ROLE_MEMBER,
                },
            )

        assert viewer.status_code == 201, viewer.text
        assert forbidden.status_code == 403
        assert forbidden.json() == {"detail": "insufficient workspace role"}

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_member_provisioning_rejects_disabled_user(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)
        workspace_id = created["workspace"]["id"]
        owner_email = f"workspace-{marker}@example.test"
        disabled_email = f"workspace-{marker}-disabled@example.test"
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    email=disabled_email,
                    name="Disabled",
                    status=USER_STATUS_DISABLED,
                )
            )
            await session.commit()

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/members",
                headers=_headers(),
                params={"owner_email": owner_email},
                json={
                    "email": disabled_email,
                    "role": MEMBERSHIP_ROLE_MEMBER,
                },
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "user disabled"}

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_member_provisioning_rejects_owner_role(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        created = await _bootstrap_workspace(marker)

        async with _async_client() as client:
            response = await client.post(
                f"/api/v1/workspaces/{created['workspace']['id']}/members",
                headers=_headers(),
                params={"owner_email": f"workspace-{marker}@example.test"},
                json={
                    "email": f"workspace-{marker}-owner@example.test",
                    "role": MEMBERSHIP_ROLE_OWNER,
                },
            )

        assert response.status_code == 422

    finally:
        await _cleanup_workspace_contract_fixture(marker)


@pytest.mark.parametrize(
    ("actual_role", "required_role", "allowed"),
    [
        (MEMBERSHIP_ROLE_OWNER, MEMBERSHIP_ROLE_ADMIN, True),
        (MEMBERSHIP_ROLE_ADMIN, MEMBERSHIP_ROLE_MEMBER, True),
        (MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_VIEWER, True),
        (MEMBERSHIP_ROLE_VIEWER, MEMBERSHIP_ROLE_VIEWER, True),
        (MEMBERSHIP_ROLE_VIEWER, MEMBERSHIP_ROLE_MEMBER, False),
        (MEMBERSHIP_ROLE_MEMBER, MEMBERSHIP_ROLE_ADMIN, False),
    ],
)
def test_membership_role_helper_allows_expected_roles(
    actual_role: str,
    required_role: str,
    allowed: bool,
) -> None:
    assert role_allows(actual_role, required_role) is allowed


def test_insufficient_workspace_role_fails() -> None:
    with pytest.raises(IdentityAccessError, match="insufficient workspace role"):
        ensure_role_allows(MEMBERSHIP_ROLE_VIEWER, MEMBERSHIP_ROLE_MEMBER)


async def test_workspace_bootstrap_requires_existing_api_key_guard(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup_workspace_contract_fixture(marker)

    try:
        async with _async_client() as client:
            response = await client.post(
                "/api/v1/workspaces/bootstrap",
                json=_bootstrap_payload(marker),
            )

        assert response.status_code == 401
        assert response.json() == {"detail": API_AUTH_FAILURE_DETAIL}
        assert "test-api-key" not in response.text

    finally:
        await _cleanup_workspace_contract_fixture(marker)


async def test_workspace_bootstrap_rejects_invalid_email(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)

    async with _async_client() as client:
        response = await client.post(
            "/api/v1/workspaces/bootstrap",
            headers=_headers(),
            json={
                **_bootstrap_payload(marker),
                "owner_email": "not-an-email",
            },
        )

    assert response.status_code == 422


def test_workspace_auth_contract_does_not_create_migration_file() -> None:
    version_files = {path.name for path in Path("migrations/versions").glob("*.py")}
    assert "f4a5b6c7d8e9_add_connection_sync_foundation.py" in version_files
    assert not any("workspace_aware_auth" in name for name in version_files)
