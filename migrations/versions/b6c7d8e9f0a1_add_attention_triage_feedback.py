"""add attention triage feedback

Revision ID: b6c7d8e9f0a1
Revises: a4d5e6f7a8b9
Create Date: 2026-05-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b6c7d8e9f0a1"
down_revision = "a4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attention_triage_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("source_object_id", sa.String(length=255), nullable=False),
        sa.Column("triage_result_id", sa.String(length=255), nullable=True),
        sa.Column("user_action", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_feedback_id"),
        "attention_triage_feedback",
        ["feedback_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_source"),
        "attention_triage_feedback",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_source_object_id"),
        "attention_triage_feedback",
        ["source_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_triage_result_id"),
        "attention_triage_feedback",
        ["triage_result_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_user_action"),
        "attention_triage_feedback",
        ["user_action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_feedback_created_at"),
        "attention_triage_feedback",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attention_triage_feedback_object_created",
        "attention_triage_feedback",
        ["source_object_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attention_triage_feedback_source_object_created",
        "attention_triage_feedback",
        ["source", "source_object_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attention_triage_feedback_source_object_created",
        table_name="attention_triage_feedback",
    )
    op.drop_index(
        "ix_attention_triage_feedback_object_created",
        table_name="attention_triage_feedback",
    )
    op.drop_index(op.f("ix_attention_triage_feedback_created_at"), table_name="attention_triage_feedback")
    op.drop_index(op.f("ix_attention_triage_feedback_user_action"), table_name="attention_triage_feedback")
    op.drop_index(op.f("ix_attention_triage_feedback_triage_result_id"), table_name="attention_triage_feedback")
    op.drop_index(op.f("ix_attention_triage_feedback_source_object_id"), table_name="attention_triage_feedback")
    op.drop_index(op.f("ix_attention_triage_feedback_source"), table_name="attention_triage_feedback")
    op.drop_index(op.f("ix_attention_triage_feedback_feedback_id"), table_name="attention_triage_feedback")
    op.drop_table("attention_triage_feedback")
