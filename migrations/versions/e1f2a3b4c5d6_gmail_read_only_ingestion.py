"""gmail read only ingestion

Revision ID: e1f2a3b4c5d6
Revises: db24cd5c2bd4
Create Date: 2026-04-25 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "db24cd5c2bd4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(255), nullable=False, unique=True),
        sa.Column("history_id", sa.String(120), nullable=True),
        sa.Column("raw_object_ref", sa.String(1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gmail_threads_thread_id", "gmail_threads", ["thread_id"])
    op.create_index("ix_gmail_threads_history_id", "gmail_threads", ["history_id"])

    op.create_table(
        "gmail_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(255), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("history_id", sa.String(120), nullable=True),
        sa.Column("snippet", sa.String(1000), nullable=True),
        sa.Column("label_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("raw_object_ref", sa.String(1000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gmail_messages_message_id", "gmail_messages", ["message_id"])
    op.create_index("ix_gmail_messages_thread_id", "gmail_messages", ["thread_id"])
    op.create_index("ix_gmail_messages_history_id", "gmail_messages", ["history_id"])

    op.create_table(
        "gmail_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("attachment_id", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("raw_object_ref", sa.String(1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("message_id", "attachment_id"),
    )
    op.create_index("ix_gmail_attachments_message_id", "gmail_attachments", ["message_id"])
    op.create_index("ix_gmail_attachments_attachment_id", "gmail_attachments", ["attachment_id"])


def downgrade() -> None:
    op.drop_table("gmail_attachments")
    op.drop_table("gmail_messages")
    op.drop_table("gmail_threads")
