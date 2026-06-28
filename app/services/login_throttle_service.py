"""DB-backed per-email login brute-force throttle (Deliverable C).

After ``login_max_failed_attempts`` consecutive failures for an email, the
account is locked for ``login_lockout_minutes``. State is keyed on the submitted
email (existing or not) so known and unknown accounts throttle identically and a
locked response never reveals account existence. A successful login resets the
counter. Survives restarts (persisted in login_attempts).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.identity_models import LoginAttempt
from app.services.identity_service import normalize_email


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def locked_until(session: AsyncSession, email: str) -> datetime | None:
    """Return the lock expiry if the email is currently locked, else None."""

    row = await session.scalar(
        select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
    )
    if row is None or row.locked_until is None:
        return None
    return row.locked_until if row.locked_until > _now() else None


async def record_failure(session: AsyncSession, email: str) -> None:
    """Increment the failure counter; lock once the threshold is reached."""

    normalized = normalize_email(email)
    now = _now()
    row = await session.scalar(
        select(LoginAttempt).where(LoginAttempt.email == normalized)
    )
    if row is None:
        row = LoginAttempt(email=normalized, failed_count=0, last_attempt_at=now)
        session.add(row)
    elif row.locked_until is not None and row.locked_until <= now:
        # A prior lock has expired — start a fresh window.
        row.failed_count = 0
        row.locked_until = None

    row.failed_count += 1
    row.last_attempt_at = now
    if row.failed_count >= settings.login_max_failed_attempts:
        row.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
    await session.flush()


async def reset(session: AsyncSession, email: str) -> None:
    """Clear the throttle state for an email (on successful login)."""

    row = await session.scalar(
        select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
    )
    if row is not None:
        row.failed_count = 0
        row.locked_until = None
        await session.flush()
