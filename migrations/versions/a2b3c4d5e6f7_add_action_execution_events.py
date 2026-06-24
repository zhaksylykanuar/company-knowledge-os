"""add action execution events

Revision ID: a2b3c4d5e6f7
Revises: e1a2b3c4d5f6
Create Date: 2026-06-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "action_execution_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "actor",
            sa.String(length=80),
            nullable=False,
            server_default="system",
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="recorded",
        ),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column(
            "event_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("idempotency_key", sa.String(length=500), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=True),
        sa.Column(
            "external_execution_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "confirmation_received",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("external_result_id", sa.String(length=255), nullable=True),
        sa.Column("external_result_url", sa.String(length=1000), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('recorded', 'blocked', 'unsupported')",
            name="ck_action_execution_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_action_execution_events_workspace_id",
        ),
        sa.ForeignKeyConstraint(
            ["action_proposal_id"],
            ["action_proposals.id"],
            name="fk_action_execution_events_action_proposal_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_action_execution_events_workspace_id"),
        "action_execution_events",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_action_execution_events_action_proposal_id"),
        "action_execution_events",
        ["action_proposal_id"],
    )
    op.create_index(
        op.f("ix_action_execution_events_event_type"),
        "action_execution_events",
        ["event_type"],
    )
    op.create_index(
        op.f("ix_action_execution_events_actor"),
        "action_execution_events",
        ["actor"],
    )
    op.create_index(
        op.f("ix_action_execution_events_status"),
        "action_execution_events",
        ["status"],
    )
    op.create_index(
        op.f("ix_action_execution_events_idempotency_key"),
        "action_execution_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_action_execution_events_provider"),
        "action_execution_events",
        ["provider"],
    )
    op.create_index(
        op.f("ix_action_execution_events_action"),
        "action_execution_events",
        ["action"],
    )
    op.create_index(
        op.f("ix_action_execution_events_external_result_id"),
        "action_execution_events",
        ["external_result_id"],
    )
    op.create_index(
        op.f("ix_action_execution_events_error_code"),
        "action_execution_events",
        ["error_code"],
    )
    op.create_index(
        op.f("ix_action_execution_events_created_at"),
        "action_execution_events",
        ["created_at"],
    )
    op.create_index(
        "ix_action_execution_events_workspace_proposal_created",
        "action_execution_events",
        ["workspace_id", "action_proposal_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("action_execution_events")
