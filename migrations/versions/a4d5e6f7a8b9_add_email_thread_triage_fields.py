"""add email thread triage fields

Revision ID: a4d5e6f7a8b9
Revises: 9f37a0b1c2d3
Create Date: 2026-05-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a4d5e6f7a8b9"
down_revision = "9f37a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_thread_states",
        sa.Column(
            "triage_category",
            sa.String(length=60),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "email_thread_states",
        sa.Column(
            "triage_action_type",
            sa.String(length=60),
            nullable=False,
            server_default="review_optional",
        ),
    )
    op.add_column(
        "email_thread_states",
        sa.Column(
            "triage_priority",
            sa.String(length=20),
            nullable=False,
            server_default="low",
        ),
    )
    op.add_column(
        "email_thread_states",
        sa.Column(
            "show_in_digest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "email_thread_states",
        sa.Column("triage_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "email_thread_states",
        sa.Column(
            "triage_confidence",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("email_thread_states", "triage_confidence")
    op.drop_column("email_thread_states", "triage_reason")
    op.drop_column("email_thread_states", "show_in_digest")
    op.drop_column("email_thread_states", "triage_priority")
    op.drop_column("email_thread_states", "triage_action_type")
    op.drop_column("email_thread_states", "triage_category")
