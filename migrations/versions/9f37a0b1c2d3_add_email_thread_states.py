"""add email thread states

Revision ID: 9f37a0b1c2d3
Revises: 8c2b0a4d9f1e
Create Date: 2026-05-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "9f37a0b1c2d3"
down_revision = "8c2b0a4d9f1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_thread_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="gmail"),
        sa.Column("thread_key", sa.String(length=255), nullable=False),
        sa.Column("provider_thread_id", sa.String(length=255), nullable=True),
        sa.Column("subject_normalized", sa.String(length=500), nullable=True),
        sa.Column("subject_display", sa.String(length=500), nullable=True),
        sa.Column(
            "participants_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_from", sa.String(length=255), nullable=True),
        sa.Column(
            "last_message_direction",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("last_message_summary", sa.Text(), nullable=True),
        sa.Column("thread_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=False, server_default="informational"),
        sa.Column("days_without_reply", sa.Integer(), nullable=True),
        sa.Column("messages_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_key", name="uq_email_thread_states_thread_key"),
    )
    op.create_index(
        op.f("ix_email_thread_states_source"),
        "email_thread_states",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_thread_states_thread_key"),
        "email_thread_states",
        ["thread_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_email_thread_states_provider_thread_id"),
        "email_thread_states",
        ["provider_thread_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_thread_states_subject_normalized"),
        "email_thread_states",
        ["subject_normalized"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_thread_states_last_message_direction"),
        "email_thread_states",
        ["last_message_direction"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_thread_states_status"),
        "email_thread_states",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_thread_states_status"), table_name="email_thread_states")
    op.drop_index(
        op.f("ix_email_thread_states_last_message_direction"),
        table_name="email_thread_states",
    )
    op.drop_index(
        op.f("ix_email_thread_states_subject_normalized"),
        table_name="email_thread_states",
    )
    op.drop_index(
        op.f("ix_email_thread_states_provider_thread_id"),
        table_name="email_thread_states",
    )
    op.drop_index(op.f("ix_email_thread_states_thread_key"), table_name="email_thread_states")
    op.drop_index(op.f("ix_email_thread_states_source"), table_name="email_thread_states")
    op.drop_table("email_thread_states")
