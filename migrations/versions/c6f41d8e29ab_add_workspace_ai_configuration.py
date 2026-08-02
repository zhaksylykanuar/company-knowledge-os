"""add encrypted workspace AI configuration

Revision ID: c6f41d8e29ab
Revises: c4d5e6f7a8b9
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6f41d8e29ab"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_ai_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            sa.String(length=40),
            server_default="openai",
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column(
            "reasoning_effort",
            sa.String(length=20),
            server_default="medium",
            nullable=False,
        ),
        sa.Column(
            "max_output_tokens",
            sa.Integer(),
            server_default="1200",
            nullable=False,
        ),
        sa.Column(
            "configuration_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("data_policy_version", sa.String(length=80), nullable=True),
        sa.Column(
            "data_policy_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "data_policy_acknowledged_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_status", sa.String(length=20), nullable=True),
        sa.Column("last_check_code", sa.String(length=80), nullable=True),
        sa.Column("last_check_model", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider = 'openai'",
            name="ck_workspace_ai_configurations_provider",
        ),
        sa.CheckConstraint(
            "reasoning_effort in ('low', 'medium', 'high')",
            name="ck_workspace_ai_configurations_reasoning_effort",
        ),
        sa.CheckConstraint(
            "max_output_tokens >= 400 and max_output_tokens <= 4000",
            name="ck_workspace_ai_configurations_output_budget",
        ),
        sa.CheckConstraint(
            "configuration_version >= 1",
            name="ck_workspace_ai_configurations_version",
        ),
        sa.CheckConstraint(
            "last_check_status is null or "
            "last_check_status in ('passed', 'failed')",
            name="ck_workspace_ai_configurations_check_status",
        ),
        sa.CheckConstraint(
            "not enabled or "
            "(encrypted_api_key is not null and "
            "data_policy_acknowledged_at is not null)",
            name="ck_workspace_ai_configurations_enabled_ready",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_ai_configurations_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["data_policy_acknowledged_by_user_id"],
            ["users.id"],
            name="fk_workspace_ai_configurations_ack_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            name="uq_workspace_ai_configurations_workspace_id",
        ),
    )
    op.create_index(
        "ix_workspace_ai_configurations_workspace_id",
        "workspace_ai_configurations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_ai_configurations_workspace_id",
        table_name="workspace_ai_configurations",
    )
    op.drop_table("workspace_ai_configurations")
