"""Server-side session lifecycle for email+password auth (Chunk 1 core).

A session is an opaque random token returned to the caller; the DB stores only
its sha256 hash, so a DB leak yields no usable tokens. Sessions are revocable
rows and validation fails once ``revoked_at`` is set or ``expires_at`` passes.

No HTTP/cookie handling lives here — that is Chunk 2. Functions take an
``AsyncSession`` so they run inside the caller's transaction.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.identity_models import User, UserSession

# secrets.token_urlsafe(32) draws 32 random bytes = 256 bits of entropy.
SESSION_TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(
    session: AsyncSession,
    user_id: UUID,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    ttl_days: int | None = None,
) -> tuple[str, UserSession]:
    """Create a session row and return ``(raw_token, UserSession)``.

    Only the token hash is persisted; the raw token is returned to the caller
    (Chunk 2 places it in an httpOnly+Secure cookie) and is never stored.
    """

    raw_token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    ttl = settings.session_ttl_days if ttl_days is None else ttl_days
    row = UserSession(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=_now() + timedelta(days=ttl),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(row)
    await session.flush()
    return raw_token, row


async def validate_session(session: AsyncSession, raw_token: str | None) -> User | None:
    """Return the owning active User for a valid token, else None.

    Rejects unknown, revoked, and expired tokens. On success, bumps
    ``last_seen_at``.
    """

    if not raw_token:
        return None
    row = await session.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(raw_token))
    )
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at <= _now():
        return None
    row.last_seen_at = _now()
    await session.flush()
    return await session.get(User, row.user_id)


async def revoke_session(session: AsyncSession, raw_token_or_id: str | UUID) -> None:
    """Revoke a single session by raw token (logout) or by session id."""

    if isinstance(raw_token_or_id, UUID):
        condition = UserSession.id == raw_token_or_id
    else:
        condition = UserSession.token_hash == _hash_token(raw_token_or_id)
    await session.execute(
        update(UserSession)
        .where(condition)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def revoke_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    """Revoke every live session for a user (logout-everywhere / compromise)."""

    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
