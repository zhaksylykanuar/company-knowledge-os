#!/usr/bin/env python
"""Provision the single founder/admin user from environment variables.

Reads the email + initial password from env (the password is NEVER printed or
committed), Argon2-hashes it via the password service, marks the user active,
and ensures the user owns a workspace. Idempotent: re-running with the same
email updates the password and reuses the existing workspace/membership — email
is unique, so no duplicate user is ever created.

This is single-admin provisioning only; User/Membership/Workspace remain
multi-user-capable, so adding teammates later is a small addition.

Env vars:
  FOUNDEROS_ADMIN_EMAIL            (required)
  FOUNDEROS_ADMIN_PASSWORD         (required; never printed/committed)
  FOUNDEROS_ADMIN_NAME             (optional)
  FOUNDEROS_ADMIN_WORKSPACE_NAME   (optional; default "Founder Workspace")
  FOUNDEROS_ADMIN_WORKSPACE_SLUG   (optional; default derived from the email)

Usage:
  FOUNDEROS_ADMIN_EMAIL=founder@example.com FOUNDEROS_ADMIN_PASSWORD=... \
      UV_NO_SYNC=1 uv run python scripts/create_admin_user.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import AsyncSessionLocal  # noqa: E402
from app.db.identity_models import (  # noqa: E402
    MEMBERSHIP_ROLE_OWNER,
    USER_STATUS_ACTIVE,
)
from app.services.identity_service import (  # noqa: E402
    create_membership,
    create_workspace,
    get_or_create_user_by_email,
    get_workspace_by_slug,
    list_workspaces_for_user,
    normalize_email,
    normalize_slug,
)
from app.services.password_service import hash_password  # noqa: E402


def _default_slug(email: str) -> str:
    local_part = normalize_email(email).split("@", 1)[0]
    safe = "".join(ch if ch.isalnum() else "-" for ch in local_part).strip("-")
    return f"{safe or 'founder'}-workspace"


async def provision_admin_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None = None,
    workspace_name: str | None = None,
    workspace_slug: str | None = None,
) -> dict[str, Any]:
    """Create/update the admin user + ensure an owned workspace (idempotent)."""

    if not email or not password:
        raise ValueError("email and password are required")

    user, user_created = await get_or_create_user_by_email(
        session, email=email, name=name
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
        slug = normalize_slug(workspace_slug) if workspace_slug else _default_slug(email)
        existing = await get_workspace_by_slug(session, slug=slug)
        if existing is None:
            workspace = await create_workspace(
                session,
                name=workspace_name or "Founder Workspace",
                slug=slug,
                created_by_user_id=user.id,
            )
            workspace_created = True
        else:
            workspace = existing
            workspace_created = False
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


async def _run(**kwargs: Any) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await provision_admin_user(session, **kwargs)
        await session.commit()
        return result


def main(argv: list[str] | None = None) -> int:
    email = os.environ.get("FOUNDEROS_ADMIN_EMAIL", "").strip()
    password = os.environ.get("FOUNDEROS_ADMIN_PASSWORD", "")
    if not email or not password:
        print(
            json.dumps(
                {
                    "status": "error",
                    "detail": "FOUNDEROS_ADMIN_EMAIL and FOUNDEROS_ADMIN_PASSWORD "
                    "must be set",
                }
            )
        )
        return 1

    result = asyncio.run(
        _run(
            email=email,
            password=password,
            name=os.environ.get("FOUNDEROS_ADMIN_NAME") or None,
            workspace_name=os.environ.get("FOUNDEROS_ADMIN_WORKSPACE_NAME") or None,
            workspace_slug=os.environ.get("FOUNDEROS_ADMIN_WORKSPACE_SLUG") or None,
        )
    )
    # The password is never included in the output.
    print(json.dumps({"status": "ok", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
