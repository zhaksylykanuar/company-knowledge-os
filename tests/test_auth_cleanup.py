from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    AccountSetupToken,
    FounderEnrollmentInvite,
    User,
    UserSession,
)
from app.services.auth_artifact_cleanup_service import (
    cleanup_expired_auth_artifacts,
)


async def test_cleanup_removes_only_expired_auth_artifacts() -> None:
    marker = uuid4().hex
    now = datetime.now(timezone.utc)
    user_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as session:
            user = User(
                email=f"auth-cleanup-{marker}@example.test",
                name="Cleanup",
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            session.add_all(
                [
                    UserSession(
                        user_id=user.id,
                        token_hash=("a" + marker)[:64].ljust(64, "a"),
                        expires_at=now - timedelta(seconds=1),
                    ),
                    UserSession(
                        user_id=user.id,
                        token_hash=("b" + marker)[:64].ljust(64, "b"),
                        expires_at=now + timedelta(hours=1),
                    ),
                    AccountSetupToken(
                        user_id=user.id,
                        token_hash=("c" + marker)[:64].ljust(64, "c"),
                        expires_at=now - timedelta(seconds=1),
                    ),
                    AccountSetupToken(
                        user_id=user.id,
                        token_hash=("d" + marker)[:64].ljust(64, "d"),
                        expires_at=now + timedelta(hours=1),
                    ),
                    FounderEnrollmentInvite(
                        token_hash=("e" + marker)[:64].ljust(64, "e"),
                        expires_at=now - timedelta(seconds=1),
                    ),
                    FounderEnrollmentInvite(
                        token_hash=("f" + marker)[:64].ljust(64, "f"),
                        expires_at=now + timedelta(hours=1),
                    ),
                ]
            )
            await session.commit()

        await cleanup_expired_auth_artifacts(now=now)

        async with AsyncSessionLocal() as session:
            sessions = list(
                await session.scalars(
                    select(UserSession).where(UserSession.user_id == user_id)
                )
            )
            setup_tokens = list(
                await session.scalars(
                    select(AccountSetupToken).where(
                        AccountSetupToken.user_id == user_id
                    )
                )
            )
            invites = list(
                await session.scalars(
                    select(FounderEnrollmentInvite).where(
                        FounderEnrollmentInvite.token_hash.in_(
                            {
                                ("e" + marker)[:64].ljust(64, "e"),
                                ("f" + marker)[:64].ljust(64, "f"),
                            }
                        )
                    )
                )
            )

        assert len(sessions) == 1
        assert sessions[0].expires_at > now
        assert len(setup_tokens) == 1
        assert setup_tokens[0].expires_at > now
        assert len(invites) == 1
        assert invites[0].expires_at > now
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(FounderEnrollmentInvite).where(
                    FounderEnrollmentInvite.token_hash.in_(
                        {
                            ("e" + marker)[:64].ljust(64, "e"),
                            ("f" + marker)[:64].ljust(64, "f"),
                        }
                    )
                )
            )
            if user_id is not None:
                await session.execute(
                    delete(UserSession).where(UserSession.user_id == user_id)
                )
                await session.execute(
                    delete(AccountSetupToken).where(
                        AccountSetupToken.user_id == user_id
                    )
                )
                await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
