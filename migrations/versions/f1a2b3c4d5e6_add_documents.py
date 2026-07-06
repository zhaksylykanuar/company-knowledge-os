"""add internal documents table (§6.16 Document)

Adds the workspace-scoped internal Document module required by the MVP
(§1.5 "internal documents", §4.7 Documents flow). Documents are authored inside
founderOS (not ingested from a provider), so they live in their own canonical
table rather than ``source_records``.

Revision ID: f1a2b3c4d5e6
Revises: e9a0b1c2d3e4
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the internal ``documents`` table."""

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body_markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="draft",
            nullable=False,
        ),
        sa.Column(
            "tags",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True
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
        sa.CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name="ck_documents_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_documents_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_documents_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_documents_updated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_workspace_id"), "documents", ["workspace_id"])
    op.create_index(op.f("ix_documents_status"), "documents", ["status"])
    op.create_index(
        op.f("ix_documents_created_by_user_id"),
        "documents",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_documents_updated_by_user_id"),
        "documents",
        ["updated_by_user_id"],
    )
    op.create_index(op.f("ix_documents_created_at"), "documents", ["created_at"])
    op.create_index(
        "ix_documents_workspace_status",
        "documents",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_documents_workspace_updated_at",
        "documents",
        ["workspace_id", "updated_at"],
    )


def downgrade() -> None:
    """Drop the internal ``documents`` table."""

    op.drop_index("ix_documents_workspace_updated_at", table_name="documents")
    op.drop_index("ix_documents_workspace_status", table_name="documents")
    op.drop_index(op.f("ix_documents_created_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_updated_by_user_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_created_by_user_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_workspace_id"), table_name="documents")
    op.drop_table("documents")
