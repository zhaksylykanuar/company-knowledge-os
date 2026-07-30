"""Test-only identity factory.

Production founder creation goes through the invite-only enrollment UI. Tests
use this helper to avoid coupling authentication coverage to an operator script
or environment-carried passwords.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identity_models import MEMBERSHIP_ROLE_OWNER, USER_STATUS_ACTIVE
from app.services.identity_service import (
    create_membership,
    create_workspace,
    get_or_create_user_by_email,
    list_workspaces_for_user,
    normalize_email,
)
from app.services.password_service import hash_password


def _test_workspace_slug(email: str) -> str:
    local_part = normalize_email(email).split("@", 1)[0]
    safe = "".join(ch if ch.isalnum() else "-" for ch in local_part).strip("-")
    return f"{safe or 'founder'}-workspace"


async def provision_test_owner(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None = None,
) -> dict[str, Any]:
    user, user_created = await get_or_create_user_by_email(
        session,
        email=email,
        name=name,
    )
    user.password_hash = hash_password(password)
    user.status = USER_STATUS_ACTIVE
    await session.flush()

    memberships = await list_workspaces_for_user(session, user_id=user.id)
    if memberships:
        workspace = memberships[0].workspace
        workspace_created = False
        membership_created = False
    else:
        workspace = await create_workspace(
            session,
            name="Founder Workspace",
            slug=_test_workspace_slug(email),
            created_by_user_id=user.id,
        )
        workspace_created = True
        _membership, membership_created = await create_membership(
            session,
            workspace_id=workspace.id,
            user_id=user.id,
            role=MEMBERSHIP_ROLE_OWNER,
        )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "user_created": user_created,
        "password_updated": True,
        "workspace_id": str(workspace.id),
        "workspace_slug": workspace.slug,
        "workspace_created": workspace_created,
        "membership_created": membership_created,
    }
