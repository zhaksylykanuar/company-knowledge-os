"""add company memory checkpoints

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-27 00:00:00.000000

Only opaque signal fingerprints are persisted. Canonical source content and
evidence remain in their existing source-of-truth tables.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_memory_checkpoints",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "checkpoint_version",
            sa.String(length=40),
            server_default="temporal-checkpoint.v1",
            nullable=False,
        ),
        sa.Column("source_snapshot_id", sa.String(length=80), nullable=False),
        sa.Column(
            "observed_through_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "event_fingerprints",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "checkpoint_version = 'temporal-checkpoint.v1'",
            name="ck_company_memory_checkpoints_version",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_company_memory_checkpoints_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        "ix_company_memory_checkpoints_workspace_updated_at",
        "company_memory_checkpoints",
        ["workspace_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_memory_checkpoints_workspace_updated_at",
        table_name="company_memory_checkpoints",
    )
    op.drop_table("company_memory_checkpoints")
