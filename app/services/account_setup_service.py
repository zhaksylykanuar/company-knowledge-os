"""One-time local account setup tokens for teammate onboarding.

Raw setup tokens are generated with high entropy and returned to the caller once.
Only sha256 hashes are persisted, matching the session-token storage rule.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identity_models import (
    ACCOUNT_SETUP_TOKEN_PURPOSE_TEAM_INVITE,
    USER_STATUS_ACTIVE,
    AccountSetupToken,
    User,
)

SETUP_TOKEN_BYTES = 32
DEFAULT_SETUP_TOKEN_TTL_DAYS = 7


class AccountSetupTokenError(ValueError):
    pass


@dataclass(frozen=True)
class CreatedAccountSetupToken:
    raw_token: str
    row: AccountSetupToken


def hash_setup_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_account_setup_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    created_by_user_id: UUID | None,
    ttl_days: int = DEFAULT_SETUP_TOKEN_TTL_DAYS,
) -> CreatedAccountSetupToken:
    """Create a one-time setup token for a user with no local password."""

    user = await session.get(User, user_id)
    if user is None or user.status != USER_STATUS_ACTIVE:
        raise AccountSetupTokenError("user not active")
    if user.password_hash is not None:
        raise AccountSetupTokenError("user already has a password")

    now = _now()
    await session.execute(
        update(AccountSetupToken)
        .where(AccountSetupToken.user_id == user_id)
        .where(AccountSetupToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )

    raw_token = secrets.token_urlsafe(SETUP_TOKEN_BYTES)
    row = AccountSetupToken(
        user_id=user_id,
        created_by_user_id=created_by_user_id,
        token_hash=hash_setup_token(raw_token),
        purpose=ACCOUNT_SETUP_TOKEN_PURPOSE_TEAM_INVITE,
        expires_at=now + timedelta(days=ttl_days),
    )
    session.add(row)
    await session.flush()
    return CreatedAccountSetupToken(raw_token=raw_token, row=row)


async def complete_account_setup_token(
    session: AsyncSession,
    *,
    raw_token: str,
    password_hash: str,
) -> User:
    """Consume a setup token, set the user's local password, and return the user."""

    if not raw_token:
        raise AccountSetupTokenError("setup token is required")
    row = await session.scalar(
        select(AccountSetupToken).where(
            AccountSetupToken.token_hash == hash_setup_token(raw_token)
        )
    )
    now = _now()
    if row is None or row.consumed_at is not None or row.expires_at <= now:
        raise AccountSetupTokenError("setup token is invalid or expired")

    user = await session.get(User, row.user_id)
    if user is None or user.status != USER_STATUS_ACTIVE:
        raise AccountSetupTokenError("user not active")

    user.password_hash = password_hash
    row.consumed_at = now
    await session.flush()
    return user
