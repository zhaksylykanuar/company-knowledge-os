"""add extraction tables

Revision ID: db24cd5c2bd4
Revises: d7ab50f1b82e
Create Date: 2026-04-25 23:59:56.124357
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "db24cd5c2bd4"
down_revision: Union[str, Sequence[str], None] = "d7ab50f1b82e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_run_id", sa.String(120), nullable=False, unique=True),
        sa.Column("runner_name", sa.String(120), nullable=False),
        sa.Column("source_document_id", sa.String(255), nullable=True),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="completed"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agent_runs_agent_run_id", "agent_runs", ["agent_run_id"])

    op.create_table(
        "extracted_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("item_type", sa.String(50), nullable=False, server_default="task"),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("due_date", sa.String(80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_event_id", sa.String(120), nullable=True),
        sa.Column("source_document_id", sa.String(255), nullable=True),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_extracted_tasks_source_event_id", "extracted_tasks", ["source_event_id"])
    op.create_index("ix_extracted_tasks_source_document_id", "extracted_tasks", ["source_document_id"])
    op.create_index("ix_extracted_tasks_chunk_id", "extracted_tasks", ["chunk_id"])

    op.create_table(
        "extracted_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("decision", sa.String(1000), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_event_id", sa.String(120), nullable=True),
        sa.Column("source_document_id", sa.String(255), nullable=True),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "extracted_risks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(80), nullable=False, server_default="medium"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_event_id", sa.String(120), nullable=True),
        sa.Column("source_document_id", sa.String(255), nullable=True),
        sa.Column("chunk_id", sa.String(255), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("extracted_risks")
    op.drop_table("extracted_decisions")
    op.drop_table("extracted_tasks")
    op.drop_table("agent_runs")
