"""Login brute-force throttle (Deliverable C)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy import delete, select, update

from app.api import auth_routes
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
from app.services import login_rate_limit_service
from app.services.login_rate_limit_service import (
    LoginAdmissionUnavailable,
    acquire_login_admission,
    login_admission_controller,
)
from app.services.login_throttle_service import reset_cleanup_schedule_for_tests
from tests.identity_factory import provision_test_owner

PASSWORD = "throttle-correct-pw"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _provision(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await provision_test_owner(session, email=email, password=PASSWORD, name="F")
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
        "/api/v1/auth/login",
        headers={"Origin": "http://127.0.0.1:3000"},
        json={"email": email, "password": password},
    )


async def test_consecutive_failures_do_not_let_an_attacker_lock_out_the_owner() -> None:
    marker = uuid4().hex[:10]
    email = f"throttle-{marker}@example.test"
    await _provision(email)
    try:
        async with _client() as client:
            for _ in range(settings.login_max_failed_attempts):
                resp = await _login(client, email, "wrong")
                assert resp.status_code == 401
            # The attacker is throttled, but a correct credential still succeeds
            # and resets the target's counter.
            owner = await _login(client, email, PASSWORD)
            assert owner.status_code == 200

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
            )
        assert row is not None and row.failed_count == 0 and row.locked_until is None
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


async def test_locked_unknown_email_still_runs_one_dummy_verification(
    monkeypatch,
) -> None:
    email = f"locked-ghost-{uuid4().hex}@example.test"
    calls = 0

    def count_verification(_plaintext: str, stored_hash: str | None) -> bool:
        nonlocal calls
        calls += 1
        assert stored_hash is not None and stored_hash.startswith("$argon2id$")
        return False

    try:
        async with _client() as client:
            for _ in range(settings.login_max_failed_attempts):
                assert (await _login(client, email, "wrong")).status_code == 401
            monkeypatch.setattr(auth_routes, "verify_password", count_verification)
            locked = await _login(client, email, "wrong")

        assert locked.status_code == 429
        assert calls == 1
    finally:
        await _cleanup(email)


async def test_concurrent_first_failures_increment_once_each_and_lock(
    monkeypatch,
) -> None:
    """Distinct login transactions cannot lose increments or race row creation."""

    marker = uuid4().hex[:10]
    email = f"concurrent-ghost-{marker}@example.test"
    attempt_count = settings.login_max_failed_attempts
    all_ready = asyncio.Event()
    counter_lock = asyncio.Lock()
    ready_count = 0
    original_record_failure = auth_routes.record_login_failure

    async def synchronized_record_failure(session, submitted_email: str) -> None:
        nonlocal ready_count
        async with counter_lock:
            ready_count += 1
            if ready_count == attempt_count:
                all_ready.set()
        await asyncio.wait_for(all_ready.wait(), timeout=5)
        await original_record_failure(session, submitted_email)

    monkeypatch.setattr(
        auth_routes,
        "record_login_failure",
        synchronized_record_failure,
    )

    try:
        async with _client() as client:
            responses = await asyncio.gather(
                *(_login(client, email, "wrong") for _ in range(attempt_count))
            )

            assert [response.status_code for response in responses] == [
                401
            ] * attempt_count
            assert (await _login(client, email, "wrong")).status_code == 429

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
            )

        assert row is not None
        assert row.failed_count == attempt_count
        assert row.locked_until is not None
        assert row.locked_until > datetime.now(timezone.utc)
    finally:
        await _cleanup(email)


async def test_production_admission_blocks_rotating_emails_before_argon(
    monkeypatch,
) -> None:
    emails = [f"rotate-{uuid4().hex}@example.test" for _ in range(3)]
    verification_calls = 0

    def count_verification(_plaintext: str, _stored_hash: str | None) -> bool:
        nonlocal verification_calls
        verification_calls += 1
        return False

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "login_rate_limit_per_ip", 2)
    monkeypatch.setattr(settings, "login_rate_limit_global", 10)
    monkeypatch.setattr(settings, "login_max_concurrent_attempts", 4)
    monkeypatch.setattr(auth_routes, "verify_password", count_verification)
    login_admission_controller.reset()
    try:
        async with _client() as client:
            first = await _login(client, emails[0], "wrong")
            second = await _login(client, emails[1], "wrong")
            blocked = await _login(client, emails[2], "wrong")

        assert [first.status_code, second.status_code, blocked.status_code] == [
            401,
            401,
            429,
        ]
        assert verification_calls == 2
        assert blocked.headers["retry-after"] == str(
            settings.login_rate_limit_window_seconds
        )
    finally:
        login_admission_controller.reset()
        for email in emails:
            await _cleanup(email)


def test_production_admission_enforces_global_and_concurrency_budgets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_per_ip", 10)
    monkeypatch.setattr(settings, "login_rate_limit_global", 10)
    monkeypatch.setattr(settings, "login_max_concurrent_attempts", 2)
    login_admission_controller.reset()
    try:
        first = login_admission_controller.acquire("client-a")
        second = login_admission_controller.acquire("client-b")
        assert first is not None
        assert second is not None
        assert login_admission_controller.acquire("client-c") is None
        first.release()
        second.release()

        monkeypatch.setattr(settings, "login_rate_limit_global", 2)
        login_admission_controller.reset()
        one = login_admission_controller.acquire("client-a")
        two = login_admission_controller.acquire("client-b")
        assert one is not None
        assert two is not None
        one.release()
        two.release()
        assert login_admission_controller.acquire("client-c") is None
    finally:
        login_admission_controller.reset()


async def test_every_public_token_endpoint_uses_pre_hash_admission(
    monkeypatch,
) -> None:
    calls = 0

    async def reject_admission(_client_key: str | None):
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(
        settings,
        "cors_allowed_origins",
        "http://127.0.0.1:3000",
    )
    monkeypatch.setattr(
        auth_routes,
        "acquire_login_admission",
        reject_admission,
    )
    origin = {"Origin": "http://127.0.0.1:3000"}
    async with _client() as client:
        login = await client.post(
            "/api/v1/auth/login",
            headers=origin,
            json={"email": "admission@example.test", "password": "password"},
        )
        enroll = await client.post(
            "/api/v1/auth/enroll",
            headers=origin,
            json={
                "token": "invite",
                "email": "admission@example.test",
                "password": "password",
                "workspace_name": "Admission",
                "workspace_slug": "admission",
            },
        )
        setup = await client.post(
            "/api/v1/auth/setup-password",
            headers=origin,
            json={"token": "setup", "new_password": "password"},
        )

    assert [login.status_code, enroll.status_code, setup.status_code] == [
        429,
        429,
        429,
    ]
    assert calls == 3


def test_client_ip_uses_forwarding_only_from_an_explicit_trusted_proxy(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "10.0.0.0/8")
    headers = [(b"x-forwarded-for", b"203.0.113.8, 10.0.0.5")]

    trusted = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": ("10.0.0.5", 1234),
        }
    )
    untrusted = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
            "client": ("192.0.2.4", 1234),
        }
    )

    assert auth_routes._client_ip(trusted) == "203.0.113.8"
    assert auth_routes._client_ip(untrusted) == "192.0.2.4"

    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    assert auth_routes._client_ip(trusted) == "10.0.0.5"


async def test_redis_admission_hashes_client_identity_and_releases_atomically(
    monkeypatch,
) -> None:
    raw_client = "203.0.113.9"
    calls: list[tuple[object, ...]] = []

    class FakeRedisClient:
        closed = False

        async def eval(self, *args: object) -> int:
            calls.append(args)
            return 1

        async def aclose(self) -> None:
            self.closed = True

    fake_client = FakeRedisClient()

    class FakeRedis:
        @staticmethod
        def from_url(*_args: object, **_kwargs: object) -> FakeRedisClient:
            return fake_client

    monkeypatch.setattr(login_rate_limit_service, "Redis", FakeRedis)
    monkeypatch.setattr(settings, "login_rate_limit_backend", "redis")

    admission = await acquire_login_admission(raw_client)
    assert admission is not None
    acquire_call_blob = repr(calls[0])
    assert raw_client not in acquire_call_blob

    await login_rate_limit_service.release_login_admission(admission)
    assert len(calls) == 2
    assert fake_client.closed is True


async def test_redis_admission_fails_closed_when_shared_store_is_unavailable(
    monkeypatch,
) -> None:
    class FailingRedisClient:
        async def eval(self, *_args: object) -> int:
            raise RedisError("unavailable")

        async def aclose(self) -> None:
            return None

    class FailingRedis:
        @staticmethod
        def from_url(*_args: object, **_kwargs: object) -> FailingRedisClient:
            return FailingRedisClient()

    monkeypatch.setattr(login_rate_limit_service, "Redis", FailingRedis)
    monkeypatch.setattr(settings, "login_rate_limit_backend", "redis")

    with pytest.raises(LoginAdmissionUnavailable):
        await acquire_login_admission("203.0.113.10")


async def test_failure_recording_removes_stale_throttle_rows() -> None:
    stale_email = f"stale-{uuid4().hex}@example.test"
    fresh_email = f"fresh-{uuid4().hex}@example.test"
    old = datetime(2000, 1, 1, tzinfo=timezone.utc)
    try:
        reset_cleanup_schedule_for_tests()
        async with AsyncSessionLocal() as session:
            session.add(
                LoginAttempt(
                    email=stale_email,
                    failed_count=1,
                    last_attempt_at=old,
                    updated_at=old,
                )
            )
            await session.commit()

        async with _client() as client:
            assert (await _login(client, fresh_email, "wrong")).status_code == 401

        async with AsyncSessionLocal() as session:
            stale = await session.scalar(
                select(LoginAttempt).where(LoginAttempt.email == stale_email)
            )
        assert stale is None
    finally:
        reset_cleanup_schedule_for_tests()
        await _cleanup(stale_email)
        await _cleanup(fresh_email)


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
            assert (await _login(client, email, "still-wrong")).status_code == 429

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
