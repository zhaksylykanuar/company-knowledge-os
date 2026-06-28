"""Server-side session lifecycle contract (against PostgreSQL).

Mirrors the DB-fixture pattern in tests/test_sync_layer_idempotency.py.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update

from app.db.base import AsyncSessionLocal
from app.db.identity_models import User, UserSession
from app.services.session_service import (
    create_session,
    revoke_all_for_user,
    revoke_session,
    validate_session,
)


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _seed_user(marker: str) -> UUID:
    async with AsyncSessionLocal() as session:
        user = User(email=f"auth-session-{marker}@example.test", name="Auth User")
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()
        return user_id


async def _cleanup(user_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_create_then_validate_returns_user_and_bumps_last_seen() -> None:
    marker = uuid4().hex[:10]
    user_id = await _seed_user(marker)
    try:
        async with AsyncSessionLocal() as session:
            raw_token, _row = await create_session(session, user_id)
            await session.commit()

        async with AsyncSessionLocal() as session:
            user = await validate_session(session, raw_token)
            await session.commit()
        assert user is not None
        assert user.id == user_id

        async with AsyncSessionLocal() as session:
            row = await session.scalar(
                select(UserSession).where(UserSession.token_hash == _token_hash(raw_token))
            )
        assert row is not None and row.last_seen_at is not None
    finally:
        await _cleanup(user_id)


async def test_db_stores_only_the_token_hash_not_the_raw_token() -> None:
    marker = uuid4().hex[:10]
    user_id = await _seed_user(marker)
    try:
        async with AsyncSessionLocal() as session:
            raw_token, row = await create_session(session, user_id)
            stored_hash = row.token_hash
            await session.commit()

        expected = _token_hash(raw_token)
        assert stored_hash == expected
        assert stored_hash != raw_token
        assert len(raw_token) >= 43  # token_urlsafe(32) -> >= 256 bits entropy

        async with AsyncSessionLocal() as session:
            by_raw = await session.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.token_hash == raw_token)
            )
            by_hash = await session.scalar(
                select(func.count())
                .select_from(UserSession)
                .where(UserSession.token_hash == expected)
            )
        assert by_raw == 0  # raw token is never persisted
        assert by_hash == 1
    finally:
        await _cleanup(user_id)


async def test_validate_after_revoke_returns_none() -> None:
    marker = uuid4().hex[:10]
    user_id = await _seed_user(marker)
    try:
        async with AsyncSessionLocal() as session:
            raw_token, _row = await create_session(session, user_id)
            await session.commit()
        async with AsyncSessionLocal() as session:
            await revoke_session(session, raw_token)
            await session.commit()
        async with AsyncSessionLocal() as session:
            assert await validate_session(session, raw_token) is None
    finally:
        await _cleanup(user_id)


async def test_validate_after_expiry_returns_none() -> None:
    marker = uuid4().hex[:10]
    user_id = await _seed_user(marker)
    try:
        async with AsyncSessionLocal() as session:
            raw_token, _row = await create_session(session, user_id)
            await session.commit()
        # Force the session into the past.
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(UserSession)
                .where(UserSession.token_hash == _token_hash(raw_token))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            assert await validate_session(session, raw_token) is None
    finally:
        await _cleanup(user_id)


async def test_revoke_all_for_user_invalidates_every_session() -> None:
    marker = uuid4().hex[:10]
    user_id = await _seed_user(marker)
    try:
        tokens: list[str] = []
        async with AsyncSessionLocal() as session:
            for _ in range(3):
                raw_token, _row = await create_session(session, user_id)
                tokens.append(raw_token)
            await session.commit()
        async with AsyncSessionLocal() as session:
            await revoke_all_for_user(session, user_id)
            await session.commit()
        async with AsyncSessionLocal() as session:
            for raw_token in tokens:
                assert await validate_session(session, raw_token) is None
    finally:
        await _cleanup(user_id)


async def test_unknown_and_missing_token_returns_none() -> None:
    async with AsyncSessionLocal() as session:
        assert await validate_session(session, "not-a-real-token") is None
        assert await validate_session(session, None) is None
