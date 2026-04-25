"""core audit foundation

Revision ID: d7ab50f1b82e
Revises:
Create Date: 2026-04-25 21:53:13.014654
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d7ab50f1b82e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("trace_id", sa.String(120), nullable=False),
        sa.Column("before_ref", sa.String(500), nullable=True),
        sa.Column("after_ref", sa.String(500), nullable=True),
        sa.Column("agent_run_id", sa.String(120), nullable=True),
        sa.Column("approval_id", sa.String(120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_correlation_id", "audit_logs", ["correlation_id"])
    op.create_index("ix_audit_logs_trace_id", "audit_logs", ["trace_id"])

    op.create_table(
        "ingested_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(120), nullable=False, unique=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(500), nullable=False, unique=True),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("trace_id", sa.String(120), nullable=False),
        sa.Column("raw_object_ref", sa.String(500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(40), nullable=False, server_default="received"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ingested_events_idempotency_key", "ingested_events", ["idempotency_key"])
    op.create_index("ix_ingested_events_source", "ingested_events", ["source_system", "source_object_id"])
    op.create_index("ix_ingested_events_correlation_id", "ingested_events", ["correlation_id"])
    op.create_index("ix_ingested_events_trace_id", "ingested_events", ["trace_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_id", sa.String(255), nullable=False, unique=True),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("raw_object_ref", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("modified_at", sa.String(80), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_system", "source_object_id", "content_hash"),
    )
    op.create_index("ix_source_documents_source_document_id", "source_documents", ["source_document_id"])
    op.create_index("ix_source_documents_source", "source_documents", ["source_system", "source_object_id"])
    op.create_index("ix_source_documents_content_hash", "source_documents", ["content_hash"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_id", sa.String(255), nullable=False),
        sa.Column("chunk_id", sa.String(255), nullable=False),
        sa.Column("source_system", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(255), nullable=False),
        sa.Column("raw_object_ref", sa.String(1000), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_document_id", "chunk_id"),
    )
    op.create_index("ix_document_chunks_source_document_id", "document_chunks", ["source_document_id"])
    op.create_index("ix_document_chunks_source", "document_chunks", ["source_system", "source_object_id"])
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("source_documents")
    op.drop_table("ingested_events")
    op.drop_table("audit_logs")
