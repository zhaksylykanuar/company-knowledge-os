"""add attention triage results

Revision ID: c8d9e0f1a2b3
Revises: b6c7d8e9f0a1
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attention_triage_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("triage_result_id", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_object_id", sa.String(length=255), nullable=False),
        sa.Column("activity_item_id", sa.String(length=255), nullable=True),
        sa.Column("attention_class", sa.String(length=60), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("show_in_digest", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("deadline", sa.String(length=120), nullable=True),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_attention_triage_results_triage_result_id"),
        "attention_triage_results",
        ["triage_result_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_attention_triage_results_source"),
        "attention_triage_results",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_source_object_id"),
        "attention_triage_results",
        ["source_object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_activity_item_id"),
        "attention_triage_results",
        ["activity_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_attention_class"),
        "attention_triage_results",
        ["attention_class"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_priority"),
        "attention_triage_results",
        ["priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_show_in_digest"),
        "attention_triage_results",
        ["show_in_digest"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attention_triage_results_created_at"),
        "attention_triage_results",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attention_triage_results_object_created",
        "attention_triage_results",
        ["source_object_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attention_triage_results_source_object_created",
        "attention_triage_results",
        ["source", "source_object_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attention_triage_results_source_object_created",
        table_name="attention_triage_results",
    )
    op.drop_index(
        "ix_attention_triage_results_object_created",
        table_name="attention_triage_results",
    )
    op.drop_index(op.f("ix_attention_triage_results_created_at"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_show_in_digest"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_priority"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_attention_class"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_activity_item_id"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_source_object_id"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_source"), table_name="attention_triage_results")
    op.drop_index(op.f("ix_attention_triage_results_triage_result_id"), table_name="attention_triage_results")
    op.drop_table("attention_triage_results")
