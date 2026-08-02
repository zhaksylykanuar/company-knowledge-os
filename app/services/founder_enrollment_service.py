"""Invite-only enrollment for the first founder and company workspace.

The operator receives the opaque invite token once.  Persistence contains only
its SHA-256 digest.  Consumption locks the invite row so concurrent requests
cannot both create a founder, then creates all identity rows in the caller's
single transaction.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    FounderEnrollmentInvite,
    Membership,
    User,
    Workspace,
)
from app.services.identity_service import (
    create_membership,
    create_user,
    create_workspace,
    get_user_by_email,
    get_workspace_by_slug,
    normalize_email,
    normalize_slug,
)
from app.services.password_service import hash_password

FOUNDER_INVITE_TOKEN_BYTES = 32
DEFAULT_FOUNDER_INVITE_TTL_HOURS = 72
MAX_FOUNDER_INVITE_TTL_HOURS = 168
INVALID_FOUNDER_INVITE = "founder invite is invalid or expired"
FOUNDER_ENROLLMENT_CONFLICT = "email or workspace slug already exists"
FOUNDER_INVITE_REVOCATION_FAILURE = "founder invite not found or already consumed"


class InvalidFounderInviteError(ValueError):
    """Raised for every unknown, expired, or already-consumed invite."""


class FounderEnrollmentConflictError(ValueError):
    """Raised when enrollment would reuse an existing identity boundary."""


class FounderInviteRevocationError(ValueError):
    """Raised when an invite cannot be revoked by its durable identifier."""


@dataclass(frozen=True)
class CreatedFounderInvite:
    raw_token: str
    row: FounderEnrollmentInvite


@dataclass(frozen=True)
class FounderEnrollment:
    user: User
    workspace: Workspace
    membership: Membership
    invite: FounderEnrollmentInvite


def hash_founder_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_founder_invite(
    session: AsyncSession,
    *,
    ttl_hours: int = DEFAULT_FOUNDER_INVITE_TTL_HOURS,
) -> CreatedFounderInvite:
    """Create an operator-issued one-time founder invitation."""

    if ttl_hours <= 0 or ttl_hours > MAX_FOUNDER_INVITE_TTL_HOURS:
        raise ValueError(
            f"ttl_hours must be between 1 and {MAX_FOUNDER_INVITE_TTL_HOURS}"
        )
    raw_token = secrets.token_urlsafe(FOUNDER_INVITE_TOKEN_BYTES)
    row = FounderEnrollmentInvite(
        token_hash=hash_founder_invite_token(raw_token),
        expires_at=_now() + timedelta(hours=ttl_hours),
    )
    session.add(row)
    await session.flush()
    return CreatedFounderInvite(raw_token=raw_token, row=row)


async def consume_founder_invite(
    session: AsyncSession,
    *,
    raw_token: str,
    email: str,
    name: str | None,
    plaintext_password: str,
    workspace_name: str,
    workspace_slug: str,
) -> FounderEnrollment:
    """Lock and consume an invite while creating the full founder identity."""

    if not raw_token:
        raise InvalidFounderInviteError(INVALID_FOUNDER_INVITE)
    invite = await session.scalar(
        select(FounderEnrollmentInvite)
        .where(
            FounderEnrollmentInvite.token_hash
            == hash_founder_invite_token(raw_token)
        )
        .with_for_update()
    )
    now = _now()
    if (
        invite is None
        or invite.consumed_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= now
    ):
        raise InvalidFounderInviteError(INVALID_FOUNDER_INVITE)

    normalized_email = normalize_email(email)
    normalized_slug = normalize_slug(workspace_slug)
    if (
        await get_user_by_email(session, email=normalized_email) is not None
        or await get_workspace_by_slug(session, slug=normalized_slug) is not None
    ):
        raise FounderEnrollmentConflictError(FOUNDER_ENROLLMENT_CONFLICT)

    user = await create_user(
        session,
        email=normalized_email,
        name=name,
        # Argon2 runs only after the invite has been locked and proven valid.
        # This prevents arbitrary public tokens from amplifying CPU work.  The
        # plaintext remains an in-memory argument and is never logged/persisted.
        password_hash=hash_password(plaintext_password),
    )
    workspace = await create_workspace(
        session,
        name=workspace_name,
        slug=normalized_slug,
        created_by_user_id=user.id,
    )
    membership, created = await create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        role=MEMBERSHIP_ROLE_OWNER,
    )
    if not created:  # Defensive: both rows are new in this transaction.
        raise FounderEnrollmentConflictError(FOUNDER_ENROLLMENT_CONFLICT)

    invite.consumed_at = now
    invite.consumed_by_user_id = user.id
    invite.consumed_workspace_id = workspace.id
    await session.flush()
    return FounderEnrollment(
        user=user,
        workspace=workspace,
        membership=membership,
        invite=invite,
    )


async def revoke_founder_invite(
    session: AsyncSession,
    *,
    invite_id: UUID,
) -> FounderEnrollmentInvite:
    """Revoke an unconsumed invite by durable ID without needing its raw token."""

    invite = await session.scalar(
        select(FounderEnrollmentInvite)
        .where(FounderEnrollmentInvite.id == invite_id)
        .with_for_update()
    )
    if invite is None or invite.consumed_at is not None:
        raise FounderInviteRevocationError(FOUNDER_INVITE_REVOCATION_FAILURE)
    if invite.revoked_at is None:
        invite.revoked_at = _now()
        await session.flush()
    return invite
