"""Login brute-force throttle (Deliverable C)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    LoginAttempt,
    Membership,
    User,
    UserSession,
    Workspace,
)
from app.main import app
from app.services.identity_service import get_user_by_email, normalize_email
from scripts.create_admin_user import provision_admin_user

PASSWORD = "throttle-correct-pw"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _provision(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await provision_admin_user(session, email=email, password=PASSWORD, name="F")
        await session.commit()


async def _cleanup(email: str) -> None:
    normalized = normalize_email(email)
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(LoginAttempt).where(LoginAttempt.email == normalized)
        )
        user = await get_user_by_email(session, email=email)
        if user is not None:
            await session.execute(
                delete(UserSession).where(UserSession.user_id == user.id)
            )
            await session.execute(
                delete(Membership).where(Membership.user_id == user.id)
            )
            await session.execute(
                delete(Workspace).where(Workspace.created_by_user_id == user.id)
            )
            await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


async def test_consecutive_failures_lock_account_then_correct_password_is_429() -> None:
    marker = uuid4().hex[:10]
    email = f"throttle-{marker}@example.test"
    await _provision(email)
    try:
        async with _client() as client:
            for _ in range(settings.login_max_failed_attempts):
                resp = await _login(client, email, "wrong")
                assert resp.status_code == 401
            # Now locked: even the CORRECT password is refused with 429.
            locked = await _login(client, email, PASSWORD)
            assert locked.status_code == 429
    finally:
        await _cleanup(email)


async def test_lock_applies_to_unknown_email_without_revealing_existence() -> None:
    # An unknown email throttles identically (no account enumeration).
    marker = uuid4().hex[:10]
    email = f"ghost-{marker}@example.test"
    try:
        async with _client() as client:
            for _ in range(settings.login_max_failed_attempts):
                resp = await _login(client, email, "wrong")
                assert resp.status_code == 401
            locked = await _login(client, email, "wrong")
            assert locked.status_code == 429
    finally:
        await _cleanup(email)


async def test_successful_login_resets_the_failure_counter() -> None:
    marker = uuid4().hex[:10]
    email = f"throttle-{marker}@example.test"
    await _provision(email)
    try:
        async with _client() as client:
            # Stay BELOW the threshold, then succeed.
            for _ in range(settings.login_max_failed_attempts - 1):
                assert (await _login(client, email, "wrong")).status_code == 401
            assert (await _login(client, email, PASSWORD)).status_code == 200

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
            )
        assert row is not None and row.failed_count == 0 and row.locked_until is None
    finally:
        await _cleanup(email)


async def test_lock_expires_after_cooldown_then_correct_password_works() -> None:
    marker = uuid4().hex[:10]
    email = f"throttle-{marker}@example.test"
    await _provision(email)
    try:
        async with _client() as client:
            for _ in range(settings.login_max_failed_attempts):
                await _login(client, email, "wrong")
            assert (await _login(client, email, PASSWORD)).status_code == 429

        # Simulate the cooldown elapsing.
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(LoginAttempt)
                .where(LoginAttempt.email == normalize_email(email))
                .values(locked_until=datetime(2000, 1, 1, tzinfo=timezone.utc))
            )
            await session.commit()

        async with _client() as client:
            assert (await _login(client, email, PASSWORD)).status_code == 200
    finally:
        await _cleanup(email)
