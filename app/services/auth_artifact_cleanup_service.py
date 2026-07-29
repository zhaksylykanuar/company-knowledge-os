"""Bounded cleanup for expired authentication artifacts.

The worker removes unusable bearer-token hashes and expired sessions. It never
reads or logs token values, user identities, request metadata, or provider data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    AccountSetupToken,
    FounderEnrollmentInvite,
    UserSession,
)

_LOGGER = logging.getLogger("founderos.auth_cleanup")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def cleanup_expired_auth_artifacts(
    *,
    now: datetime | None = None,
) -> None:
    """Delete expired token hashes and no-longer-useful session rows."""

    cleanup_time = now or _now()
    revoked_cutoff = cleanup_time - timedelta(
        hours=settings.revoked_session_retention_hours
    )
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(UserSession).where(
                or_(
                    UserSession.expires_at <= cleanup_time,
                    UserSession.revoked_at <= revoked_cutoff,
                )
            )
        )
        await session.execute(
            delete(AccountSetupToken).where(
                AccountSetupToken.expires_at <= cleanup_time
            )
        )
        await session.execute(
            delete(FounderEnrollmentInvite).where(
                FounderEnrollmentInvite.expires_at <= cleanup_time
            )
        )
        await session.commit()


async def run_auth_artifact_cleanup(
    stop_event: asyncio.Event,
) -> None:
    """Run cleanup immediately and then on the configured bounded interval."""

    while not stop_event.is_set():
        try:
            await cleanup_expired_auth_artifacts()
        except SQLAlchemyError:
            _LOGGER.error("auth_artifact_cleanup_failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.auth_artifact_cleanup_interval_seconds,
            )
        except TimeoutError:
            continue
