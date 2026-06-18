"""add agent proposals and metric snapshots

Revision ID: b7c8d9e0f1a2
Revises: a5f1c2d3e4b6
Create Date: 2026-06-12 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a5f1c2d3e4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=120), nullable=False),
        sa.Column("agent", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_proposals_proposal_id"),
        "agent_proposals",
        ["proposal_id"],
        unique=True,
    )
    op.create_index(op.f("ix_agent_proposals_agent"), "agent_proposals", ["agent"])
    op.create_index(op.f("ix_agent_proposals_kind"), "agent_proposals", ["kind"])
    op.create_index(op.f("ix_agent_proposals_status"), "agent_proposals", ["status"])
    op.create_index(
        op.f("ix_agent_proposals_created_at"), "agent_proposals", ["created_at"]
    )

    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=160), nullable=False),
        sa.Column("captured_on", sa.String(length=10), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metric_key",
            "scope",
            "captured_on",
            name="uq_metric_snapshots_key_scope_day",
        ),
    )
    op.create_index(
        op.f("ix_metric_snapshots_metric_key"), "metric_snapshots", ["metric_key"]
    )
    op.create_index(op.f("ix_metric_snapshots_scope"), "metric_snapshots", ["scope"])
    op.create_index(
        op.f("ix_metric_snapshots_captured_on"), "metric_snapshots", ["captured_on"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("metric_snapshots")
    op.drop_table("agent_proposals")
