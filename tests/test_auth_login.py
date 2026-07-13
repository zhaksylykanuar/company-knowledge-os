"""Login / logout / me + session-cookie route protection (Deliverable A)."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api import auth_routes
from app.api.auth_routes import GENERIC_LOGIN_FAILURE
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    LoginAttempt,
    USER_STATUS_DISABLED,
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
    email = f"nobody-{uuid4().hex}@example.test"
    async with _client() as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "x"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_LOGIN_FAILURE


async def test_login_runs_one_argon_verification_for_unknown_identity(
    monkeypatch,
) -> None:
    email = f"timing-{uuid4().hex}@example.test"
    calls: list[tuple[str, str | None]] = []

    def record_verification(plaintext: str, stored_hash: str | None) -> bool:
        calls.append((plaintext, stored_hash))
        return False

    monkeypatch.setattr(auth_routes, "verify_password", record_verification)
    try:
        async with _client() as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            )

        assert response.status_code == 401
        assert len(calls) == 1
        assert calls[0][0] == "wrong-password"
        assert calls[0][1] is not None
        assert calls[0][1].startswith("$argon2id$")
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
            await session.commit()


async def test_login_rejects_oversized_public_inputs_before_database_use() -> None:
    async with _client() as client:
        oversized_email = await client.post(
            "/api/v1/auth/login",
            json={"email": f"{'x' * 309}@example.test", "password": "valid-input"},
        )
        oversized_password = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.test", "password": "x" * 257},
        )

    assert oversized_email.status_code == 422
    assert oversized_password.status_code == 422


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


async def test_existing_session_is_rejected_after_user_is_disabled() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id, email = await _seed_founder(marker)
    try:
        async with _client() as client:
            login = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            assert login.status_code == 200
            raw_token = client.cookies.get(settings.session_cookie_name)
            assert raw_token is not None

            async with AsyncSessionLocal() as session:
                user = await session.get(User, user_id)
                assert user is not None
                user.status = USER_STATUS_DISABLED
                await session.commit()

            after_disable = await client.get("/api/v1/auth/me")

        assert after_disable.status_code == 401
        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(UserSession).where(UserSession.token_hash == _token_hash(raw_token))
            )
        assert row is not None and row.revoked_at is not None
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
