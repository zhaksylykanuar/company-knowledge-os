"""add action proposal foundation

Revision ID: f5a6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("briefing_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_provider", sa.String(length=40), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "created_by",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
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
            "target_provider in ('github', 'internal')",
            name="ck_action_proposals_target_provider",
        ),
        sa.CheckConstraint(
            "action_type in ('create_github_issue', 'internal_todo')",
            name="ck_action_proposals_action_type",
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'approved', 'rejected', 'executed', 'failed')",
            name="ck_action_proposals_status",
        ),
        sa.CheckConstraint(
            "created_by in ('user', 'system', 'ai')",
            name="ck_action_proposals_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_action_proposals_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_action_proposals_created_by_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_action_proposals_approved_by_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by_user_id"],
            ["users.id"],
            name="fk_action_proposals_rejected_by_user_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_action_proposals_workspace_id"),
        "action_proposals",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_action_proposals_briefing_item_id"),
        "action_proposals",
        ["briefing_item_id"],
    )
    op.create_index(
        op.f("ix_action_proposals_target_provider"),
        "action_proposals",
        ["target_provider"],
    )
    op.create_index(
        op.f("ix_action_proposals_action_type"),
        "action_proposals",
        ["action_type"],
    )
    op.create_index(
        op.f("ix_action_proposals_status"),
        "action_proposals",
        ["status"],
    )
    op.create_index(
        op.f("ix_action_proposals_created_by"),
        "action_proposals",
        ["created_by"],
    )
    op.create_index(
        op.f("ix_action_proposals_created_by_user_id"),
        "action_proposals",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_action_proposals_approved_by_user_id"),
        "action_proposals",
        ["approved_by_user_id"],
    )
    op.create_index(
        op.f("ix_action_proposals_rejected_by_user_id"),
        "action_proposals",
        ["rejected_by_user_id"],
    )
    op.create_index(
        op.f("ix_action_proposals_created_at"),
        "action_proposals",
        ["created_at"],
    )
    op.create_index(
        "ix_action_proposals_workspace_status",
        "action_proposals",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_action_proposals_provider_action_type",
        "action_proposals",
        ["target_provider", "action_type"],
    )

    op.create_table(
        "action_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "provider_response",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
            "status in ('running', 'succeeded', 'failed')",
            name="ck_action_executions_status",
        ),
        sa.ForeignKeyConstraint(
            ["action_proposal_id"],
            ["action_proposals.id"],
            name="fk_action_executions_action_proposal_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_action_executions_action_proposal_id"),
        "action_executions",
        ["action_proposal_id"],
    )
    op.create_index(
        op.f("ix_action_executions_status"),
        "action_executions",
        ["status"],
    )
    op.create_index(
        op.f("ix_action_executions_external_id"),
        "action_executions",
        ["external_id"],
    )
    op.create_index(
        op.f("ix_action_executions_created_at"),
        "action_executions",
        ["created_at"],
    )
    op.create_index(
        "ix_action_executions_proposal_status",
        "action_executions",
        ["action_proposal_id", "status"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("action_executions")
    op.drop_table("action_proposals")
