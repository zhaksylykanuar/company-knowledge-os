"""Login / logout / me + session-cookie route protection (Deliverable A)."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api.auth_routes import GENERIC_LOGIN_FAILURE
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    Membership,
    User,
    UserSession,
    Workspace,
)
from app.main import app
from app.services.identity_service import (
    create_membership,
    create_user,
    create_workspace,
)
from app.services.password_service import hash_password

PASSWORD = "founder-test-pw"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _seed_founder(marker: str) -> tuple[UUID, UUID, str]:
    async with AsyncSessionLocal() as session:
        user = await create_user(
            session,
            email=f"founder-{marker}@example.test",
            name="Founder",
            password_hash=hash_password(PASSWORD),
        )
        workspace = await create_workspace(
            session,
            name=f"Founder WS {marker}",
            slug=f"founder-ws-{marker}",
            created_by_user_id=user.id,
        )
        await create_membership(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            role=MEMBERSHIP_ROLE_OWNER,
        )
        ids = (user.id, workspace.id, user.email)
        await session.commit()
        return ids


async def _cleanup(user_id: UUID, workspace_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        await session.execute(delete(Membership).where(Membership.user_id == user_id))
        await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_login_sets_cookie_and_creates_session() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == email
        assert settings.session_cookie_name in response.cookies
        async with AsyncSessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.user_id == user_id)
            )
        assert count == 1
    finally:
        await _cleanup(user_id, workspace_id)


async def test_login_wrong_password_is_generic_401_without_cookie() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-pw"}
            )
        assert response.status_code == 401
        assert response.json()["detail"] == GENERIC_LOGIN_FAILURE
        assert settings.session_cookie_name not in response.cookies
    finally:
        await _cleanup(user_id, workspace_id)


async def test_login_unknown_email_is_same_generic_401() -> None:
    # No account enumeration: unknown email yields the same generic failure.
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.test", "password": "x"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_FAILURE


async def test_me_requires_cookie_and_returns_user_and_workspace() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            unauth = await client.get("/api/v1/auth/me")
            assert unauth.status_code == 401

            await client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            authed = await client.get("/api/v1/auth/me")
        assert authed.status_code == 200
        body = authed.json()
        assert body["user"]["email"] == email
        assert any(ws["id"] == str(workspace_id) for ws in body["workspaces"])
    finally:
        await _cleanup(user_id, workspace_id)


async def test_logout_revokes_session_and_clears_cookie() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            await client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            raw_token = client.cookies.get(settings.session_cookie_name)
            logout = await client.post("/api/v1/auth/logout")
            assert logout.status_code == 200
            after = await client.get("/api/v1/auth/me")
        assert after.status_code == 401
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(UserSession).where(UserSession.token_hash == _token_hash(raw_token))
            )
        assert row is not None and row.revoked_at is not None
    finally:
        await _cleanup(user_id, workspace_id)


async def test_session_cookie_authorizes_product_route_without_owner_email() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            await client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            # Session cookie resolves the workspace via membership — no owner_email.
            response = await client.get(f"/api/v1/workspaces/{workspace_id}")
        assert response.status_code == 200
    finally:
        await _cleanup(user_id, workspace_id)
