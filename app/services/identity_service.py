from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    Membership,
    User,
    Workspace,
)


ROLE_ORDER = {
    MEMBERSHIP_ROLE_VIEWER: 10,
    MEMBERSHIP_ROLE_MEMBER: 20,
    MEMBERSHIP_ROLE_ADMIN: 30,
    MEMBERSHIP_ROLE_OWNER: 40,
}


class IdentityConflictError(ValueError):
    pass


class IdentityAccessError(PermissionError):
    pass


@dataclass(frozen=True)
class WorkspaceMembership:
    user: User
    workspace: Workspace
    membership: Membership


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_slug(slug: str) -> str:
    return slug.strip().lower()


def role_allows(actual_role: str, required_role: str) -> bool:
    actual_rank = ROLE_ORDER.get(actual_role)
    required_rank = ROLE_ORDER.get(required_role)
    return actual_rank is not None and required_rank is not None and actual_rank >= required_rank


def ensure_role_allows(actual_role: str, required_role: str) -> None:
    if not role_allows(actual_role, required_role):
        raise IdentityAccessError("insufficient workspace role")


async def get_user_by_email(session: AsyncSession, *, email: str) -> User | None:
    normalized_email = normalize_email(email)
    return await session.scalar(select(User).where(User.email == normalized_email))


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    name: str | None = None,
    password_hash: str | None = None,
) -> User:
    user = User(
        email=normalize_email(email),
        name=name.strip() if isinstance(name, str) and name.strip() else None,
        password_hash=password_hash,
        status=USER_STATUS_ACTIVE,
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_user_by_email(
    session: AsyncSession,
    *,
    email: str,
    name: str | None = None,
) -> tuple[User, bool]:
    user = await get_user_by_email(session, email=email)
    if user is not None:
        return user, False
    return await create_user(session, email=email, name=name), True


async def get_workspace_by_slug(session: AsyncSession, *, slug: str) -> Workspace | None:
    normalized_slug = normalize_slug(slug)
    return await session.scalar(select(Workspace).where(Workspace.slug == normalized_slug))


async def create_workspace(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    created_by_user_id: UUID,
) -> Workspace:
    workspace = Workspace(
        name=name.strip(),
        slug=normalize_slug(slug),
        created_by_user_id=created_by_user_id,
    )
    session.add(workspace)
    await session.flush()
    return workspace


async def create_membership(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    role: str = MEMBERSHIP_ROLE_MEMBER,
) -> tuple[Membership, bool]:
    existing = await session.scalar(
        select(Membership)
        .where(Membership.workspace_id == workspace_id)
        .where(Membership.user_id == user_id)
    )
    if existing is not None:
        return existing, False

    membership = Membership(workspace_id=workspace_id, user_id=user_id, role=role)
    session.add(membership)
    await session.flush()
    return membership, True


async def bootstrap_workspace_for_owner(
    session: AsyncSession,
    *,
    owner_email: str,
    owner_name: str | None,
    workspace_name: str,
    workspace_slug: str,
) -> WorkspaceMembership:
    user, _created = await get_or_create_user_by_email(
        session,
        email=owner_email,
        name=owner_name,
    )
    if user.status == USER_STATUS_DISABLED:
        raise IdentityAccessError("user disabled")

    existing_workspace = await get_workspace_by_slug(session, slug=workspace_slug)
    if existing_workspace is not None:
        raise IdentityConflictError("workspace slug already exists")

    workspace = await create_workspace(
        session,
        name=workspace_name,
        slug=workspace_slug,
        created_by_user_id=user.id,
    )
    membership, _membership_created = await create_membership(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        role=MEMBERSHIP_ROLE_OWNER,
    )
    return WorkspaceMembership(user=user, workspace=workspace, membership=membership)


async def list_workspaces_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[WorkspaceMembership]:
    rows = (
        await session.execute(
            select(User, Workspace, Membership)
            .join(Membership, Membership.user_id == User.id)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .where(User.id == user_id)
            .order_by(Workspace.created_at.desc())
        )
    ).all()
    return [
        WorkspaceMembership(user=user, workspace=workspace, membership=membership)
        for user, workspace, membership in rows
    ]


async def get_workspace_for_user(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceMembership | None:
    row = (
        await session.execute(
            select(User, Workspace, Membership)
            .join(Membership, Membership.user_id == User.id)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .where(User.id == user_id)
            .where(Workspace.id == workspace_id)
        )
    ).one_or_none()
    if row is None:
        return None
    user, workspace, membership = row
    return WorkspaceMembership(user=user, workspace=workspace, membership=membership)


async def user_has_workspace_access(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> bool:
    return (
        await get_workspace_for_user(
            session,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        is not None
    )
