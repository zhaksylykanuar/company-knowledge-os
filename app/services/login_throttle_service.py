"""DB-backed per-email login brute-force throttle (Deliverable C).

After ``login_max_failed_attempts`` consecutive failures for an email, the
account is locked for ``login_lockout_minutes``. State is keyed on the submitted
email (existing or not) so known and unknown accounts throttle identically and a
locked response never reveals account existence. A successful login resets the
counter. Survives restarts (persisted in login_attempts).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from uuid import uuid4

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.identity_models import LoginAttempt
from app.services.identity_service import normalize_email

_CLEANUP_INTERVAL_SECONDS = 60 * 60
_cleanup_schedule_lock = Lock()
_last_cleanup_monotonic: float | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim_stale_cleanup() -> bool:
    global _last_cleanup_monotonic
    now = monotonic()
    with _cleanup_schedule_lock:
        if (
            _last_cleanup_monotonic is not None
            and now - _last_cleanup_monotonic < _CLEANUP_INTERVAL_SECONDS
        ):
            return False
        _last_cleanup_monotonic = now
        return True


def reset_cleanup_schedule_for_tests() -> None:
    global _last_cleanup_monotonic
    with _cleanup_schedule_lock:
        _last_cleanup_monotonic = None


async def locked_until(session: AsyncSession, email: str) -> datetime | None:
    """Return the lock expiry if the email is currently locked, else None."""

    row = await session.scalar(
        select(LoginAttempt).where(LoginAttempt.email == normalize_email(email))
    )
    if row is None or row.locked_until is None:
        return None
    return row.locked_until if row.locked_until > _now() else None


async def record_failure(session: AsyncSession, email: str) -> None:
    """Atomically increment failures; lock once the threshold is reached."""

    normalized = normalize_email(email)
    now = _now()
    if _claim_stale_cleanup():
        await session.execute(
            delete(LoginAttempt).where(
                LoginAttempt.updated_at
                < now - timedelta(hours=settings.login_attempt_retention_hours)
            )
        )
    lock_expires_at = now + timedelta(minutes=settings.login_lockout_minutes)
    threshold = settings.login_max_failed_attempts

    expired_lock = LoginAttempt.locked_until.is_not(None) & (
        LoginAttempt.locked_until <= now
    )
    currently_locked = LoginAttempt.locked_until.is_not(None) & (
        LoginAttempt.locked_until > now
    )
    next_failed_count = case(
        (expired_lock, 1),
        else_=LoginAttempt.failed_count + 1,
    )
    next_locked_until = case(
        # Requests admitted just before a concurrent request established the
        # lock may arrive here later. Count them, but do not extend the lock.
        (currently_locked, LoginAttempt.locked_until),
        (next_failed_count >= threshold, lock_expires_at),
        else_=None,
    )

    statement = (
        insert(LoginAttempt)
        .values(
            id=uuid4(),
            email=normalized,
            failed_count=1,
            locked_until=lock_expires_at if threshold <= 1 else None,
            last_attempt_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[LoginAttempt.email],
            set_={
                "failed_count": next_failed_count,
                "locked_until": next_locked_until,
                "last_attempt_at": now,
                "updated_at": now,
            },
        )
    )
    await session.execute(statement)


async def reset(session: AsyncSession, email: str) -> None:
    """Clear the throttle state for an email (on successful login)."""

    await session.execute(
        update(LoginAttempt)
        .where(LoginAttempt.email == normalize_email(email))
        .values(failed_count=0, locked_until=None, updated_at=_now())
    )
