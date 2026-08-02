"""add founder enrollment invites

Revision ID: b4d5e6f7a8c9
Revises: a3c4d5e6f7b8
Create Date: 2026-07-13 00:00:00.000000

Invite rows store only a SHA-256 token digest. Consumption metadata is nullable
until the one-time invite is used atomically by the enrollment transaction.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b4d5e6f7a8c9"
down_revision: Union[str, Sequence[str], None] = "a3c4d5e6f7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "founder_enrollment_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("consumed_workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "consumed_at is not null or "
            "(consumed_by_user_id is null and consumed_workspace_id is null)",
            name="ck_founder_enrollment_invites_consumption_metadata",
        ),
        sa.CheckConstraint(
            "consumed_at is null or revoked_at is null",
            name="ck_founder_enrollment_invites_not_consumed_and_revoked",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_user_id"],
            ["users.id"],
            name="fk_founder_enrollment_invites_consumed_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_workspace_id"],
            ["workspaces.id"],
            name="fk_founder_enrollment_invites_consumed_workspace_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_founder_enrollment_invites_token_hash",
        ),
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_consumed_at"),
        "founder_enrollment_invites",
        ["consumed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_consumed_by_user_id"),
        "founder_enrollment_invites",
        ["consumed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_consumed_workspace_id"),
        "founder_enrollment_invites",
        ["consumed_workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_expires_at"),
        "founder_enrollment_invites",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_revoked_at"),
        "founder_enrollment_invites",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_founder_enrollment_invites_token_hash"),
        "founder_enrollment_invites",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_founder_enrollment_invites_token_hash"),
        table_name="founder_enrollment_invites",
    )
    op.drop_index(
        op.f("ix_founder_enrollment_invites_revoked_at"),
        table_name="founder_enrollment_invites",
    )
    op.drop_index(
        op.f("ix_founder_enrollment_invites_expires_at"),
        table_name="founder_enrollment_invites",
    )
    op.drop_index(
        op.f("ix_founder_enrollment_invites_consumed_workspace_id"),
        table_name="founder_enrollment_invites",
    )
    op.drop_index(
        op.f("ix_founder_enrollment_invites_consumed_by_user_id"),
        table_name="founder_enrollment_invites",
    )
    op.drop_index(
        op.f("ix_founder_enrollment_invites_consumed_at"),
        table_name="founder_enrollment_invites",
    )
    op.drop_table("founder_enrollment_invites")
