from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.identity_models import (
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    USER_STATUS_ACTIVE,
    WORKSPACE_STATUS_ACTIVE,
    Membership,
    User,
    Workspace,
)


async def _cleanup_identity_fixture(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = (
            await session.execute(
                select(Workspace.id).where(Workspace.slug.like(f"identity-{marker}%"))
            )
        ).scalars()
        user_ids = (
            await session.execute(
                select(User.id).where(User.email.like(f"identity-{marker}%@example.test"))
            )
        ).scalars()
        workspace_id_values = list(workspace_ids)
        user_id_values = list(user_ids)
        if workspace_id_values:
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_id_values))
            )
        if user_id_values:
            await session.execute(
                delete(Membership).where(Membership.user_id.in_(user_id_values))
            )
        if workspace_id_values:
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_id_values))
            )
        if user_id_values:
            await session.execute(delete(User).where(User.id.in_(user_id_values)))
        await session.commit()


def test_identity_models_register_with_metadata() -> None:
    assert User.__tablename__ == "users"
    assert Workspace.__tablename__ == "workspaces"
    assert Membership.__tablename__ == "memberships"


async def test_create_user_workspace_and_membership() -> None:
    marker = uuid4().hex
    await _cleanup_identity_fixture(marker)

    try:
        async with AsyncSessionLocal() as session:
            user = User(
                email=f"identity-{marker}@example.test",
                name="Founder",
            )
            session.add(user)
            await session.flush()

            workspace = Workspace(
                name="Founder Workspace",
                slug=f"identity-{marker}",
                created_by_user_id=user.id,
            )
            session.add(workspace)
            await session.flush()

            membership = Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )
            session.add(membership)
            await session.commit()

        async with AsyncSessionLocal() as session:
            stored_user = await session.scalar(select(User).where(User.id == user.id))
            stored_workspace = await session.scalar(
                select(Workspace).where(Workspace.id == workspace.id)
            )
            stored_membership = await session.scalar(
                select(Membership).where(Membership.id == membership.id)
            )

        assert isinstance(stored_user.id, UUID)
        assert stored_user.email == f"identity-{marker}@example.test"
        assert stored_user.status == USER_STATUS_ACTIVE
        assert stored_user.password_hash is None
        assert stored_workspace.slug == f"identity-{marker}"
        assert stored_workspace.status == WORKSPACE_STATUS_ACTIVE
        assert stored_workspace.created_by_user_id == stored_user.id
        assert stored_membership.workspace_id == stored_workspace.id
        assert stored_membership.user_id == stored_user.id
        assert stored_membership.role == MEMBERSHIP_ROLE_OWNER

    finally:
        await _cleanup_identity_fixture(marker)


async def test_membership_default_role_is_member() -> None:
    marker = uuid4().hex
    await _cleanup_identity_fixture(marker)

    try:
        async with AsyncSessionLocal() as session:
            user = User(email=f"identity-{marker}@example.test", name="Member")
            session.add(user)
            await session.flush()
            workspace = Workspace(
                name="Member Workspace",
                slug=f"identity-{marker}",
                created_by_user_id=user.id,
            )
            session.add(workspace)
            await session.flush()
            membership = Membership(workspace_id=workspace.id, user_id=user.id)
            session.add(membership)
            await session.commit()

        async with AsyncSessionLocal() as session:
            stored = await session.scalar(
                select(Membership).where(Membership.id == membership.id)
            )
        assert stored.role == MEMBERSHIP_ROLE_MEMBER

    finally:
        await _cleanup_identity_fixture(marker)


@pytest.mark.parametrize(
        ("first", "second", "message"),
        [
            ("user_email", "user_email", "uq_users_email"),
            ("workspace_slug", "workspace_slug", "uq_workspaces_slug"),
            ("membership", "membership", "uq_memberships_workspace_user"),
        ],
    )
async def test_identity_unique_constraints(first: str, second: str, message: str) -> None:
    marker = uuid4().hex
    await _cleanup_identity_fixture(marker)

    try:
        async with AsyncSessionLocal() as session:
            user = User(email=f"identity-{marker}@example.test", name="Owner")
            session.add(user)
            await session.flush()
            workspace = Workspace(
                name="Owner Workspace",
                slug=f"identity-{marker}",
                created_by_user_id=user.id,
            )
            session.add(workspace)
            await session.flush()
            session.add(Membership(workspace_id=workspace.id, user_id=user.id))
            await session.flush()

            if first == second == "user_email":
                session.add(User(email=f"identity-{marker}@example.test", name="Dupe"))
            elif first == second == "workspace_slug":
                session.add(
                    Workspace(
                        name="Dupe Workspace",
                        slug=f"identity-{marker}",
                        created_by_user_id=user.id,
                    )
                )
            else:
                session.add(Membership(workspace_id=workspace.id, user_id=user.id))

            with pytest.raises(IntegrityError, match=message):
                await session.commit()
            await session.rollback()

    finally:
        await _cleanup_identity_fixture(marker)


async def test_membership_rejects_unknown_role() -> None:
    marker = uuid4().hex
    await _cleanup_identity_fixture(marker)

    try:
        async with AsyncSessionLocal() as session:
            user = User(email=f"identity-{marker}@example.test", name="Owner")
            session.add(user)
            await session.flush()
            workspace = Workspace(
                name="Owner Workspace",
                slug=f"identity-{marker}",
                created_by_user_id=user.id,
            )
            session.add(workspace)
            await session.flush()
            session.add(
                Membership(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="superuser",
                )
            )

            with pytest.raises(IntegrityError, match="ck_memberships_role"):
                await session.commit()
            await session.rollback()

    finally:
        await _cleanup_identity_fixture(marker)


async def test_identity_migration_tables_exist_in_database() -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public'
                    and table_name in ('users', 'workspaces', 'memberships')
                    """
                )
            )
        ).scalars()

    assert set(rows) == {"users", "workspaces", "memberships"}
