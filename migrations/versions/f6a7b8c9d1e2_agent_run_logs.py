"""agent run logs and finding update reason

Revision ID: f6a7b8c9d1e2
Revises: e5f6a7b8c9d1
Create Date: 2026-06-13 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d1e2"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "second_opinion_findings",
        sa.Column("last_update_reason", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "metric_snapshots",
        sa.Column("last_update_reason", sa.String(length=40), nullable=True),
    )

    op.create_table(
        "agent_run_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("agent", sa.String(length=80), nullable=False),
        sa.Column("agent_version", sa.String(length=40), nullable=False),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_watermark", sa.String(length=120), nullable=True),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column(
            "updated_from_new_evidence", sa.Integer(), nullable=False
        ),
        sa.Column(
            "updated_from_clock_recalculation", sa.Integer(), nullable=False
        ),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("auto_resolved", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_run_logs_run_id"), "agent_run_logs", ["run_id"]
    )
    op.create_index(op.f("ix_agent_run_logs_agent"), "agent_run_logs", ["agent"])
    op.create_index(
        op.f("ix_agent_run_logs_created_at"), "agent_run_logs", ["created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("agent_run_logs")
    op.drop_column("metric_snapshots", "last_update_reason")
    op.drop_column("second_opinion_findings", "last_update_reason")
