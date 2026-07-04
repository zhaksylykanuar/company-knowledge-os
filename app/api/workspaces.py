from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth import CurrentActor, require_operator_or_user
from app.api.workspace_auth import (
    WorkspaceAccess,
    require_workspace_access,
    require_workspace_role,
)
from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_VIEWER,
    USER_STATUS_DISABLED,
    Membership,
    User,
    Workspace,
)
from app.services.identity_service import (
    IdentityAccessError,
    IdentityConflictError,
    ProvisionedWorkspaceMember,
    WorkspaceMembership,
    bootstrap_workspace_for_owner,
    get_user_by_email,
    list_workspaces_for_user,
    list_workspace_members,
    provision_workspace_member,
)
from app.services.password_service import hash_password


router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRead(BaseModel):
    id: UUID
    email: str
    name: str | None
    status: str


class WorkspaceRead(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str


class MembershipRead(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str


class WorkspaceBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    owner_email: str = Field(min_length=3, max_length=320)
    owner_name: str | None = Field(default=None, max_length=255)
    workspace_name: str = Field(min_length=1, max_length=255)
    workspace_slug: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$",
    )

    @field_validator("owner_email")
    @classmethod
    def validate_owner_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_RE.fullmatch(normalized):
            raise ValueError("invalid owner_email")
        return normalized

    @field_validator("workspace_slug")
    @classmethod
    def validate_workspace_slug(cls, value: str) -> str:
        return value.strip().lower()


class WorkspaceBootstrapResponse(BaseModel):
    user: UserRead
    workspace: WorkspaceRead
    membership: MembershipRead


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceRead]


class WorkspaceMemberRead(BaseModel):
    user: UserRead
    membership: MembershipRead


class WorkspaceMembersResponse(BaseModel):
    members: list[WorkspaceMemberRead]


class WorkspaceMemberProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=255)
    role: str = Field(default=MEMBERSHIP_ROLE_MEMBER)
    initial_password: str | None = Field(default=None, min_length=8, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_RE.fullmatch(normalized):
            raise ValueError("invalid email")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed_roles = {
            MEMBERSHIP_ROLE_ADMIN,
            MEMBERSHIP_ROLE_MEMBER,
            MEMBERSHIP_ROLE_VIEWER,
        }
        if normalized not in allowed_roles:
            raise ValueError("role must be admin, member, or viewer")
        return normalized


class WorkspaceMemberProvisionResponse(BaseModel):
    member: WorkspaceMemberRead
    external_invite_sent: bool
    provider_write_performed: bool
    login_credential_set: bool
    warnings: list[str]


def _user_read(user: User) -> UserRead:
    return UserRead(id=user.id, email=user.email, name=user.name, status=user.status)


def _workspace_read(workspace: Workspace) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        status=workspace.status,
    )


def _membership_read(membership: Membership) -> MembershipRead:
    return MembershipRead(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        role=membership.role,
    )


def _workspace_member_read(
    workspace_membership: WorkspaceMembership | ProvisionedWorkspaceMember,
) -> WorkspaceMemberRead:
    return WorkspaceMemberRead(
        user=_user_read(workspace_membership.user),
        membership=_membership_read(workspace_membership.membership),
    )


def _bootstrap_response(
    workspace_membership: WorkspaceMembership,
) -> WorkspaceBootstrapResponse:
    return WorkspaceBootstrapResponse(
        user=_user_read(workspace_membership.user),
        workspace=_workspace_read(workspace_membership.workspace),
        membership=_membership_read(workspace_membership.membership),
    )


async def _operator_owner_user_id(
    *,
    owner_email: str | None,
    actor: CurrentActor,
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
            detail="owner_email is required for operator workspace listing",
        )
    async with AsyncSessionLocal() as session:
        user = await get_user_by_email(session, email=owner_email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found",
            )
        if user.status == USER_STATUS_DISABLED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user disabled",
            )
        return user.id


@router.post(
    "/bootstrap",
    response_model=WorkspaceBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_workspace(
    payload: WorkspaceBootstrapRequest,
    actor: CurrentActor = Depends(require_operator_or_user),
) -> WorkspaceBootstrapResponse:
    if not actor.is_operator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="operator access required",
        )
    async with AsyncSessionLocal() as session:
        try:
            workspace_membership = await bootstrap_workspace_for_owner(
                session,
                owner_email=payload.owner_email,
                owner_name=payload.owner_name,
                workspace_name=payload.workspace_name,
                workspace_slug=payload.workspace_slug,
            )
            await session.commit()
        except IdentityConflictError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except IdentityAccessError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
    return _bootstrap_response(workspace_membership)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    owner_email: str | None = Query(default=None, min_length=3, max_length=320),
    actor: CurrentActor = Depends(require_operator_or_user),
) -> WorkspaceListResponse:
    user_id = await _operator_owner_user_id(owner_email=owner_email, actor=actor)
    async with AsyncSessionLocal() as session:
        memberships = await list_workspaces_for_user(session, user_id=user_id)
    return WorkspaceListResponse(
        workspaces=[
            _workspace_read(workspace_membership.workspace)
            for workspace_membership in memberships
        ]
    )


@router.get("/{workspace_id}", response_model=WorkspaceBootstrapResponse)
async def get_workspace(
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> WorkspaceBootstrapResponse:
    return _bootstrap_response(access.workspace_membership)


@router.get("/{workspace_id}/members", response_model=WorkspaceMembersResponse)
async def list_workspace_team_members(
    access: WorkspaceAccess = Depends(require_workspace_access),
) -> WorkspaceMembersResponse:
    async with AsyncSessionLocal() as session:
        members = await list_workspace_members(
            session,
            workspace_id=access.workspace_membership.workspace.id,
        )
    return WorkspaceMembersResponse(
        members=[_workspace_member_read(member) for member in members]
    )


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_workspace_team_member(
    payload: WorkspaceMemberProvisionRequest,
    access: WorkspaceAccess = Depends(require_workspace_role(MEMBERSHIP_ROLE_ADMIN)),
) -> WorkspaceMemberProvisionResponse:
    initial_password_hash = (
        hash_password(payload.initial_password)
        if payload.initial_password is not None
        else None
    )
    async with AsyncSessionLocal() as session:
        try:
            member = await provision_workspace_member(
                session,
                workspace_id=access.workspace_membership.workspace.id,
                email=payload.email,
                name=payload.name,
                role=payload.role,
                initial_password_hash=initial_password_hash,
            )
            await session.commit()
        except IdentityConflictError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except IdentityAccessError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
    if payload.initial_password is not None and not member.login_credential_set:
        warning = (
            "Local teammate membership created; the existing account already had a "
            "password, so no credential was changed. No email invite or external "
            "provider write was sent."
        )
    elif member.login_credential_set:
        warning = (
            "Local teammate membership created with an initial local password; the "
            "teammate can sign in and should change it. No email invite or external "
            "provider write was sent."
        )
    else:
        warning = (
            "Local teammate membership created without a login password; set an "
            "initial password so the teammate can sign in. No email invite or "
            "external provider write was sent."
        )
    return WorkspaceMemberProvisionResponse(
        member=_workspace_member_read(member),
        external_invite_sent=False,
        provider_write_performed=False,
        login_credential_set=member.login_credential_set,
        warnings=[warning],
    )
