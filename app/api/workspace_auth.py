from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status

from app.api.auth import CurrentActor, require_operator_or_user
from app.db.base import AsyncSessionLocal
from app.db.identity_models import USER_STATUS_DISABLED
from app.services.identity_service import (
    IdentityAccessError,
    WorkspaceMembership,
    ensure_role_allows,
    get_user_by_email,
    get_workspace_for_user,
)


@dataclass(frozen=True)
class WorkspaceAccess:
    actor: CurrentActor
    workspace_membership: WorkspaceMembership


async def _resolve_workspace_user_id(
    actor: CurrentActor,
    *,
    owner_email: str | None,
) -> UUID:
    if actor.user_id is not None:
        return actor.user_id
    if not actor.is_operator:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    if owner_email is None or not owner_email.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="owner_email is required for operator workspace access",
        )
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(session, email=owner_email)
        if user is None or user.status == USER_STATUS_DISABLED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace not found",
            )
        return user.id


async def require_workspace_access(
    workspace_id: UUID,
    owner_email: str | None = Query(default=None, max_length=320),
    actor: CurrentActor = Depends(require_operator_or_user),
) -> WorkspaceAccess:
    user_id = await _resolve_workspace_user_id(actor, owner_email=owner_email)
    async with AsyncSessionLocal() as session:
        workspace_membership = await get_workspace_for_user(
            session,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if workspace_membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace not found",
            )
        if workspace_membership.user.status == USER_STATUS_DISABLED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user disabled",
            )
        return WorkspaceAccess(
            actor=actor,
            workspace_membership=workspace_membership,
        )


def require_workspace_role(required_role: str):
    async def dependency(
        access: WorkspaceAccess = Depends(require_workspace_access),
    ) -> WorkspaceAccess:
        try:
            ensure_role_allows(access.workspace_membership.membership.role, required_role)
        except IdentityAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return access

    return dependency
