"""add internal document versions table (§4.7 DocumentVersion)

Adds immutable local history snapshots for internal founderOS Documents. Version
records are local-only: they preserve authored markdown + deterministic text
projection on create/update and do not call providers or LLMs.

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the internal document version history table."""

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body_markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "tags",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_document_versions_workspace_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_document_versions_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_version_number",
        ),
    )
    op.create_index(
        op.f("ix_document_versions_workspace_id"),
        "document_versions",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_document_versions_document_id"),
        "document_versions",
        ["document_id"],
    )
    op.create_index(
        op.f("ix_document_versions_created_by_user_id"),
        "document_versions",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_document_versions_created_at"),
        "document_versions",
        ["created_at"],
    )
    op.create_index(
        "ix_document_versions_workspace_document_created",
        "document_versions",
        ["workspace_id", "document_id", "created_at"],
    )


def downgrade() -> None:
    """Drop the internal document version history table."""

    op.drop_index(
        "ix_document_versions_workspace_document_created",
        table_name="document_versions",
    )
    op.drop_index(
        op.f("ix_document_versions_created_at"),
        table_name="document_versions",
    )
    op.drop_index(
        op.f("ix_document_versions_created_by_user_id"),
        table_name="document_versions",
    )
    op.drop_index(
        op.f("ix_document_versions_document_id"),
        table_name="document_versions",
    )
    op.drop_index(
        op.f("ix_document_versions_workspace_id"),
        table_name="document_versions",
    )
    op.drop_table("document_versions")
