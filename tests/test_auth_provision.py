"""Admin provisioning command + change-password endpoint (Deliverable B)."""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.db.base import AsyncSessionLocal
from app.db.identity_models import Membership, User, UserSession, Workspace
from app.main import app
from app.services.identity_service import get_user_by_email
from app.services.password_service import verify_password
from scripts.create_admin_user import provision_admin_user

OLD_PASSWORD = "old-founder-pw"
NEW_PASSWORD = "new-founder-pw"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _provision(email: str, password: str) -> dict:
    async with AsyncSessionLocal() as session:
        result = await provision_admin_user(
            session, email=email, password=password, name="Founder"
        )
        await session.commit()
        return result


async def _cleanup(email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(session, email=email)
        if user is None:
            return
        await session.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await session.execute(delete(Membership).where(Membership.user_id == user.id))
        await session.execute(
            delete(Workspace).where(Workspace.created_by_user_id == user.id)
        )
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


async def test_provision_admin_creates_user_workspace_membership_idempotently() -> None:
    marker = uuid4().hex[:10]
    email = f"admin-{marker}@example.test"
    try:
        first = await _provision(email, "pw-1")
        second = await _provision(email, "pw-2")

        assert first["user_created"] is True
        assert second["user_created"] is False
        assert first["user_id"] == second["user_id"]
        assert first["workspace_id"] == second["workspace_id"]
        assert second["workspace_created"] is False

        async with AsyncSessionLocal() as session:
            user = await get_user_by_email(session, email=email)
            membership_count = await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.user_id == user.id)
            )
        assert membership_count == 1  # no duplicate membership
        # Re-run updated the password (idempotent update, not duplicate user).
        assert verify_password("pw-2", user.password_hash) is True
        assert verify_password("pw-1", user.password_hash) is False
    finally:
        await _cleanup(email)


def test_create_admin_user_script_runs_from_repo_root_without_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("FOUNDEROS_ADMIN_EMAIL", None)
    env.pop("FOUNDEROS_ADMIN_PASSWORD", None)

    result = subprocess.run(
        [sys.executable, "scripts/create_admin_user.py"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "FOUNDEROS_ADMIN_EMAIL and FOUNDEROS_ADMIN_PASSWORD" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


async def test_change_password_rejects_wrong_current_and_accepts_correct() -> None:
    marker = uuid4().hex[:10]
    email = f"admin-{marker}@example.test"
    await _provision(email, OLD_PASSWORD)
    try:
        async with _client() as client:
            await _login(client, email, OLD_PASSWORD)
            wrong = await client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "nope", "new_password": NEW_PASSWORD},
            )
            assert wrong.status_code == 400
            ok = await client.post(
                "/api/v1/auth/change-password",
                json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            )
            assert ok.status_code == 200

        # New password works; old no longer does.
        async with _client() as client:
            assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
        async with _client() as client:
            assert (await _login(client, email, OLD_PASSWORD)).status_code == 401
    finally:
        await _cleanup(email)


async def test_change_password_revokes_other_sessions_keeps_current() -> None:
    marker = uuid4().hex[:10]
    email = f"admin-{marker}@example.test"
    await _provision(email, OLD_PASSWORD)
    try:
        async with _client() as current, _client() as other:
            await _login(current, email, OLD_PASSWORD)
            await _login(other, email, OLD_PASSWORD)
            assert (await current.get("/api/v1/auth/me")).status_code == 200
            assert (await other.get("/api/v1/auth/me")).status_code == 200

            changed = await current.post(
                "/api/v1/auth/change-password",
                json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            )
            assert changed.status_code == 200

            # Current session stays valid; the other device is logged out.
            assert (await current.get("/api/v1/auth/me")).status_code == 200
            assert (await other.get("/api/v1/auth/me")).status_code == 401
    finally:
        await _cleanup(email)
